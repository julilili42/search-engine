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
            queries[int(row[0])] = row[1].strip()
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
            qrels.setdefault(int(query_id), {})[normalize_url(url)] = int(rating)
    return qrels


def search_api_results(index_path: Path, queries: dict[int, str], top_n: int) -> tuple[dict[int, list[dict[str, object]]], list[float]]:
    from fastapi.testclient import TestClient
    from tuebingen_search.api import app

    results: dict[int, list[dict[str, object]]] = {}
    latencies: list[float] = []

    old_index_path = os.environ.get("INDEX_PATH")
    os.environ["INDEX_PATH"] = str(index_path)
    try:
        with TestClient(app) as client:
            for query_id, query in queries.items():
                start = time.perf_counter()
                response = client.get("/search", params={"q": query, "top_n": top_n})
                latencies.append((time.perf_counter() - start) * 1000)
                response.raise_for_status()
                results[query_id] = response.json()
    finally:
        if old_index_path is None:
            os.environ.pop("INDEX_PATH", None)
        else:
            os.environ["INDEX_PATH"] = old_index_path

    return results, latencies
