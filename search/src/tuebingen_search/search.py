"""Search over a serialized index."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import msgpack

from .tokenizer import tokenize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    rank: int
    score: float
    path: str
    snippet: str


@dataclass(frozen=True)
class LoadedIndex:
    documents: list[list]
    inverted_index: dict[str, list[list]]


def load_index(index_path: str) -> LoadedIndex:
    start = time.perf_counter()
    with Path(index_path).open("rb") as index_file:
        raw = msgpack.unpack(index_file, raw=False)

    index = LoadedIndex(
        documents=raw["documents"],
        inverted_index=raw["inverted_index"],
    )
    logger.info(
        "Loaded %s with %d documents in %s",
        index_path,
        len(index.documents),
        _elapsed(start),
    )
    return index


def search_index(index: LoadedIndex, query: str, top_n: int) -> list[SearchResult]:
    start = time.perf_counter()
    query_terms = sorted(set(tokenize(query)))

    if not query_terms:
        logger.warning("No searchable query terms in query.")
        return []

    logger.info("Searching for %r ...", " ".join(query_terms))

    scores: dict[int, float] = {}
    for term in query_terms:
        for doc_index, score in index.inverted_index.get(term, []):
            scores[doc_index] = scores.get(doc_index, 0.0) + score

    ranked_results = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    search_results: list[SearchResult] = []

    for rank, (doc_index, score) in enumerate(ranked_results[:top_n], start=1):
        path, _length, snippet = index.documents[doc_index]
        search_results.append(
            SearchResult(rank=rank, score=score, path=path, snippet=snippet)
        )

    logger.info("Search computation took %s", _elapsed(start))
    return search_results


def search(index_path: str, query: str, top_n: int) -> list[SearchResult]:
    return search_index(load_index(index_path), query, top_n)


def _elapsed(start: float) -> str:
    return f"{time.perf_counter() - start:.6f}s"
