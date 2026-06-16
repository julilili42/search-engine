from __future__ import annotations

import logging
import time

from .tokenizer import tokenize
from .models import SearchResult, SearchIndex
from .storage import load_index, elapsed
from collections.abc import Sequence

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
    for term in query_terms:
        for posting in index.inverted_index.get(term, []):
            scores[posting.doc_index] = scores.get(posting.doc_index, 0.0) + posting.score
            positions.setdefault(posting.doc_index, []).extend(posting.positions)

    for doc_positions in positions.values():
        doc_positions.sort()

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


def search(index_path: str, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    return search_index(load_index(index_path), query, top_n, context_size)

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

