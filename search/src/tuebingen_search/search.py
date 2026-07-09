from __future__ import annotations

import heapq
import logging
import time

from collections.abc import Sequence
from pathlib import Path

from .models import (
    DocumentScores,
    DocumentTermPositions,
    SearchIndex,
    SearchResult,
    TermPosition,
)
from .tokenizer import tokenize
from .storage import load_index, elapsed


logger = logging.getLogger(__name__)

def search_index(index: SearchIndex, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
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


def search(index_path: Path, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    return search_index(load_index(index_path), query, top_n, context_size)


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
