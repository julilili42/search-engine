from __future__ import annotations

import heapq
import logging
import os
import time

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .embeddings import embed_texts, load_embeddings
from .models import (
    DocumentScores,
    DocumentTermPositions,
    SearchIndex,
    SearchResult,
    TermPosition,
)
from .paths import DEFAULT_EMBEDDINGS_PATH
from .tokenizer import tokenize
from .storage import load_index, elapsed


logger = logging.getLogger(__name__)

RERANK_CANDIDATES = 100
# env overrides exist for benchmark sweeps (alpha tuning, RRF comparison)
ALPHA = float(os.environ.get("RERANK_ALPHA", "0.5"))
RRF_K = 60


def search_index(
    index: SearchIndex,
    query: str,
    top_n: int,
    context_size: int = 20,
    doc_embeddings: np.ndarray | None = None,
) -> list[SearchResult]:
    start = time.perf_counter()
    query_terms = set(tokenize(query))

    if not query_terms:
        logger.warning("No searchable query terms in query.")
        return []

    logger.info("Searching for %r ...", " ".join(query_terms))

    scores: DocumentScores = {}
    term_positions: DocumentTermPositions = {}

    # get scores and matching positions for query terms from inverted index
    for term in query_terms:
        for posting in index.inverted_index.get(term, []):
            scores[posting.doc_index] = scores.get(posting.doc_index, 0.0) + posting.score
            term_positions.setdefault(posting.doc_index, {})[term] = posting.positions

    for doc_index, doc_term_positions in term_positions.items():
        scores[doc_index] += proximity_bonus(doc_term_positions)

    if doc_embeddings is not None and scores:
        candidates = heapq.nlargest(max(top_n, RERANK_CANDIDATES), scores.items(), key=lambda item: item[1])
        ranked_results = rerank(candidates, doc_embeddings, embed_texts([query])[0])[:top_n]
    else:
        ranked_results = heapq.nlargest(top_n, scores.items(), key=lambda item: item[1])

    search_results: list[SearchResult] = []

    for rank, (doc_index, score) in enumerate(ranked_results, start=1):
        document = index.documents[doc_index]
        path, url, terms = document.path, document.url, document.terms
        
        snippet = generate_snippet(terms, term_positions[doc_index], context_size)

        search_results.append(
            SearchResult(rank=rank, score=score, path=path, url=url, snippet=snippet)
        )

    logger.info("Search computation took %s", elapsed(start))
    return search_results


def rerank(
    candidates: list[tuple[int, float]],
    doc_embeddings: np.ndarray,
    query_embedding: np.ndarray,
    alpha: float = ALPHA,
) -> list[tuple[int, float]]:
    doc_indices = [doc_index for doc_index, _ in candidates]
    lexical = np.array([score for _, score in candidates])

    spread = lexical.max() - lexical.min()
    lexical_norm = (lexical - lexical.min()) / spread if spread > 0 else np.zeros_like(lexical)
    cosine = doc_embeddings[doc_indices] @ query_embedding

    if os.environ.get("RERANK_FUSION") == "rrf":
        blended = reciprocal_rank_fusion(lexical, cosine)
    else:
        blended = alpha * lexical_norm + (1 - alpha) * cosine
    order = np.argsort(-blended)
    return [(doc_indices[i], float(blended[i])) for i in order]


def reciprocal_rank_fusion(lexical: np.ndarray, cosine: np.ndarray, k: int = RRF_K) -> np.ndarray:
    def ranks(scores: np.ndarray) -> np.ndarray:
        positions = np.empty(len(scores))
        positions[np.argsort(-scores)] = np.arange(1, len(scores) + 1)
        return positions

    return 1 / (k + ranks(lexical)) + 1 / (k + ranks(cosine))


def search(index_path: Path, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    index = load_index(index_path)
    doc_embeddings = load_embeddings(DEFAULT_EMBEDDINGS_PATH, index.documents)
    return search_index(index, query, top_n, context_size, doc_embeddings)


def best_window(term_positions: TermPosition) -> tuple[int, int] | None:
    if len(term_positions) < 2:
        return None

    events = sorted(
        (position, term)
        for term in term_positions
        for position in term_positions[term]
    )
    counts: dict[str, int] = {}
    left = 0
    best: tuple[int, int] | None = None

    # sliding window > each term must be included atleast once in window
    for right_position, right_term in events:
        counts[right_term] = counts.get(right_term, 0) + 1

        while len(counts) == len(term_positions):
            left_position, left_term = events[left]
            if best is None or right_position - left_position < best[1] - best[0]:
                best = (left_position, right_position)

            counts[left_term] -= 1
            if counts[left_term] == 0:
                del counts[left_term]
            left += 1

    return best


def proximity_bonus(term_positions: TermPosition, boost: float = 0.25) -> float:
    window = best_window(term_positions)
    if window is None:
        return 0.0

    extra_gap = (window[1] - window[0] + 1) - len(term_positions)
    return boost / (1 + extra_gap)


def generate_snippet(
    terms: Sequence[str],
    term_positions: TermPosition,
    context_size: int,
) -> str:
    window = best_window(term_positions)
    if window is not None:
        # center on the tightest window containing all query terms
        position = (window[0] + window[1]) // 2
    else:
        positions = [p for ps in term_positions.values() for p in ps]
        if not positions:
            return " ".join(terms[: 2 * context_size + 1])
        position = min(positions)

    start = max(0, position - context_size)
    end = min(len(terms), position + context_size + 1)

    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(terms) else ""

    return prefix + " ".join(terms[start:end]) + suffix
