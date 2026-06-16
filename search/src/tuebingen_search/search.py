from __future__ import annotations

import logging
import time

from pathlib import Path
from .tokenizer import tokenize
from .models import SearchResult, SearchIndex
from .storage import load_index, elapsed
from .html import extract_text_from_html

logger = logging.getLogger(__name__)


def search_index(index: SearchIndex, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    start = time.perf_counter()
    query_terms = set(tokenize(query))

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
        path, url = document.path, document.url
        snippet = generate_snippet(document.path, query_terms, context_size)
        search_results.append(
            SearchResult(rank=rank, score=score, path=path, url=url, snippet=snippet)
        )

    logger.info("Search computation took %s", elapsed(start))
    return search_results


def search(index_path: str, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    return search_index(load_index(index_path), query, top_n, context_size)



# TODO
# currently we have to reload the html of the top search results to generate query-based snippets.
# This could hurt performance. 
def generate_snippet(
    path: Path,
    query_terms: set[str],
    context_size: int,
) -> str:
    try:
        text = extract_text_from_html(path)
    except OSError:
        logger.warning("Could not generate snippet from %s", path, exc_info=True)
        return ""

    terms = tokenize(text)

    for index, term in enumerate(terms):
        if term in query_terms:
            start = max(0, index - context_size)
            end = min(len(terms), index + context_size + 1)

            prefix = "... " if start > 0 else ""
            suffix = " ..." if end < len(terms) else ""

            return prefix + " ".join(terms[start:end]) + suffix

    return " ".join(terms[:40])
