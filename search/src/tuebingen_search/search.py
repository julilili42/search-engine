from __future__ import annotations

import logging
import time

from .tokenizer import tokenize
from .models import SearchResult, SearchIndex
from .storage import load_index, elapsed
from collections.abc import Sequence
from pathlib import Path


logger = logging.getLogger(__name__)

def search_index(index: SearchIndex, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    start = time.perf_counter()
    query_terms = set(tokenize(query))

    if not query_terms:
        logger.warning("No searchable query terms in query.")
        return []

    logger.info("Searching for %r ...", " ".join(query_terms))

    scores: dict[int, float] = {}
    positions: dict[int, list[int]] = {}
    term_positions: dict[int, dict[str, list[int]]] = {}
    for term in query_terms:
        for posting in index.inverted_index.get(term, []):
            scores[posting.doc_index] = scores.get(posting.doc_index, 0.0) + posting.score
            positions.setdefault(posting.doc_index, []).extend(posting.positions)
            term_positions.setdefault(posting.doc_index, {})[term] = posting.positions

    for doc_positions in positions.values():
        doc_positions.sort()

    for doc_index, doc_term_positions in term_positions.items():
        scores[doc_index] += proximity_bonus(query_terms, doc_term_positions)

    ranked_results = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    search_results: list[SearchResult] = []

    for rank, (doc_index, score) in enumerate(ranked_results[:top_n], start=1):
        document = index.documents[doc_index]
        path, url, terms = document.path, document.url, document.terms
        
        snippet = generate_snippet(
            terms,
            positions[doc_index],
            context_size,
        )

        search_results.append(
            SearchResult(rank=rank, score=score, path=path, url=url, snippet=snippet)
        )

    logger.info("Search computation took %s", elapsed(start))
    return search_results


def search(index_path: Path, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    return search_index(load_index(index_path), query, top_n, context_size)


def proximity_bonus(query_terms: set[str], term_positions: dict[str, list[int]], boost: float = 0.25) -> float:
    if len(query_terms) < 2 or not query_terms.issubset(term_positions):
        return 0.0

    events = sorted(
        (position, term)
        for term in query_terms
        for position in term_positions[term]
    )
    counts: dict[str, int] = {}
    left = 0
    best_span: int | None = None

    for right_position, right_term in events:
        counts[right_term] = counts.get(right_term, 0) + 1

        while len(counts) == len(query_terms):
            left_position, left_term = events[left]
            span = right_position - left_position + 1
            best_span = span if best_span is None else min(best_span, span)

            counts[left_term] -= 1
            if counts[left_term] == 0:
                del counts[left_term]
            left += 1

    if best_span is None:
        return 0.0

    extra_gap = best_span - len(query_terms)
    return boost / (1 + extra_gap)


def generate_snippet(
    terms: Sequence[str],
    positions: list[int],
    context_size: int,
) -> str:
    if not positions:
        return " ".join(terms[:40])

    position = min(positions)

    start = max(0, position - context_size)
    end = min(len(terms), position + context_size + 1)

    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(terms) else ""

    return prefix + " ".join(terms[start:end]) + suffix
