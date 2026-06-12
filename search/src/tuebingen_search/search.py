from __future__ import annotations

import logging
import time

from .tokenizer import tokenize
from .models import SearchResult, SearchIndex
from .storage import load_index, elapsed

logger = logging.getLogger(__name__)


def search_index(index: SearchIndex, query: str, top_n: int) -> list[SearchResult]:
    start = time.perf_counter()
    query_terms = sorted(set(tokenize(query)))

    if not query_terms:
        logger.warning("No searchable query terms in query.")
        return []

    logger.info("Searching for %r ...", " ".join(query_terms))

    scores: dict[int, float] = {}
    for term in query_terms:
        for posting in index.inverted_index.get(term, []):
            scores[posting.doc_index] = scores.get(posting.doc_index, 0.0) + posting.score

    ranked_results = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    search_results: list[SearchResult] = []

    for rank, (doc_index, score) in enumerate(ranked_results[:top_n], start=1):
        document = index.documents[doc_index]
        path, snippet = document.path, document.text_snippet
        search_results.append(
            SearchResult(rank=rank, score=score, path=path, snippet=snippet)
        )

    logger.info("Search computation took %s", elapsed(start))
    return search_results


def search(index_path: str, query: str, top_n: int) -> list[SearchResult]:
    return search_index(load_index(index_path), query, top_n)


