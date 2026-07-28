from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def read_queries(path: Path) -> dict[int, str]:
    queries: dict[int, str] = {}
    with path.open(encoding="utf-8", newline="") as file:
        for row_number, row in enumerate(csv.reader(file, delimiter="\t"), start=1):
            if not row or row[0].startswith("#"):
                continue
            if len(row) != 2:
                raise ValueError(f"Invalid query format in line {row_number}: {row}")
            query_id, query = int(row[0]), row[1].strip()
            if query_id in queries:
                raise ValueError(f"Duplicate query ID in line {row_number}: {query_id}")
            if not query:
                raise ValueError(f"Empty query in line {row_number}")
            queries[query_id] = query
    return queries


def read_qrels(path: Path) -> dict[int, dict[str, int]]:
    qrels: dict[int, dict[str, int]] = {}
    with path.open(encoding="utf-8", newline="") as file:
        for row_number, row in enumerate(csv.reader(file, delimiter="\t"), start=1):
            if not row or row[0].startswith("#"):
                continue
            if len(row) != 3:
                raise ValueError(f"Invalid qrels format in line {row_number}: {row}")
            query_id, url, rating = row
            query_id, rating = int(query_id), int(rating)
            url = normalize_url(url)
            if not 0 <= rating <= 3:
                raise ValueError(f"Invalid rating in line {row_number}: {rating}")
            if url in qrels.get(query_id, {}):
                raise ValueError(f"Duplicate qrel in line {row_number}: {query_id}, {url}")
            qrels.setdefault(query_id, {})[url] = rating
    return qrels


def search_api_results(
    index_path: Path,
    queries: dict[int, str],
    top_n: int,
    *,
    use_proximity: bool = True,
    use_semantic: bool = True,
    alpha: float = 0.7,
    beta: float = 0.3,
) -> tuple[dict[int, list[dict[str, object]]], list[float]]:
    from fastapi.testclient import TestClient
    from tuebingen_search.api import app

    results: dict[int, list[dict[str, object]]] = {}
    latencies: list[float] = []

    old_index_path = os.environ.get("INDEX_PATH")
    os.environ["INDEX_PATH"] = str(index_path)
    try:
        with TestClient(app) as client:
            if queries:
                client.get(
                    "/search",
                    params={
                        "q": next(iter(queries.values())),
                        "top_n": top_n,
                        "proximity": use_proximity,
                        "semantic": use_semantic,
                        "alpha": alpha,
                        "beta": beta,
                    },
                ).raise_for_status()
            for query_id, query in queries.items():
                start = time.perf_counter()
                response = client.get(
                    "/search",
                    params={
                        "q": query,
                        "top_n": top_n,
                        "proximity": use_proximity,
                        "semantic": use_semantic,
                        "alpha": alpha,
                        "beta": beta,
                    },
                )
                latencies.append((time.perf_counter() - start) * 1000)
                response.raise_for_status()
                results[query_id] = response.json()
    finally:
        if old_index_path is None:
            os.environ.pop("INDEX_PATH", None)
        else:
            os.environ["INDEX_PATH"] = old_index_path

    return results, latencies
