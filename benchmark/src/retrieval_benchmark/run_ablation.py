from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from .extract import read_queries, search_api_results
from .paths import DEFAULT_INDEX_PATH, DEFAULT_QUERIES_PATH, OUTPUT_DIR
from tuebingen_search.paths import DEFAULT_EMBEDDINGS_PATH
from tuebingen_search.search import ALPHA, RERANK_CANDIDATES

TOP_N = 100
POOL_DEPTH = 20
VARIANTS = {
    "bm25f": (False, False),
    "bm25f-proximity": (True, False),
    "bm25f-semantic": (False, True),
    "full": (True, True),
}


def run() -> None:
    queries = read_queries(DEFAULT_QUERIES_PATH)
    runs: dict[str, dict[str, object]] = {}

    for name, (use_proximity, use_semantic) in VARIANTS.items():
        results, latencies = search_api_results(
            DEFAULT_INDEX_PATH,
            queries,
            TOP_N,
            use_proximity=use_proximity,
            use_semantic=use_semantic,
        )
        payload = {
            "variant": name,
            "top_n": TOP_N,
            "use_proximity": use_proximity,
            "use_semantic": use_semantic,
            "latencies_ms": dict(zip(queries, latencies)),
            "results": results,
        }
        variant_dir = OUTPUT_DIR / name
        variant_dir.mkdir(parents=True, exist_ok=True)
        (variant_dir / "results.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        runs[name] = payload

    write_pool(runs, queries)
    write_manifest()


def write_pool(runs: dict[str, dict[str, object]], queries: dict[int, str]) -> None:
    pooled: dict[tuple[int, str], dict[str, object]] = {}
    for variant, run_data in runs.items():
        results = run_data["results"]
        assert isinstance(results, dict)
        for query_id, query_results in results.items():
            for rank, result in enumerate(query_results[:POOL_DEPTH], start=1):
                url = result.get("url")
                if not url:
                    continue
                key = (int(query_id), str(url))
                row = pooled.setdefault(
                    key,
                    {
                        "query_id": query_id,
                        "query": queries[int(query_id)],
                        "url": url,
                        "title": result.get("title") or "",
                        "snippet": result.get("snippet") or "",
                        "path": result.get("path") or "",
                        "ranks": {},
                    },
                )
                row["ranks"][variant] = rank

    with (OUTPUT_DIR / "judging_pool.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerow(
            ["query_id", "query", "url", "title", "snippet", "path", *VARIANTS]
        )
        rows = sorted(
            pooled.values(),
            key=lambda item: (int(item["query_id"]), str(item["url"])),
        )
        for row in rows:
            ranks = row.pop("ranks")
            writer.writerow([*row.values(), *(ranks.get(variant, "") for variant in VARIANTS)])


def write_manifest() -> None:
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    manifest = {
        "top_n": TOP_N,
        "pool_depth": POOL_DEPTH,
        "rerank_candidates": RERANK_CANDIDATES,
        "lexical_weight": ALPHA,
        "index_sha256": sha256(DEFAULT_INDEX_PATH),
        "embeddings_sha256": sha256(DEFAULT_EMBEDDINGS_PATH),
        "queries_sha256": sha256(DEFAULT_QUERIES_PATH),
        "variants": {
            name: {
                "use_proximity": proximity,
                "use_semantic": semantic,
            }
            for name, (proximity, semantic) in VARIANTS.items()
        },
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
