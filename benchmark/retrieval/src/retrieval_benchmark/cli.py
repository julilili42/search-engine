from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path

from tuebingen_search.paths import DEFAULT_EMBEDDINGS_PATH
from tuebingen_search.search import ALPHA, BETA, RERANK_CANDIDATES

from .extract import normalize_url, read_qrels, read_queries, search_api_results
from .metrics import compute_metrics

ROOT = Path(__file__).resolve().parents[4]
INDEX = ROOT / "data/index/index.bin"
BENCHMARK = ROOT / "benchmark/retrieval"
TOP_N = 100
POOL_DEPTH = 20
DEV_VARIANTS = {
    "bm25f": (False, False),
    "bm25f-proximity": (True, False),
    "bm25f-semantic": (False, True),
    "full": (True, True),
}
TEST_VARIANTS = {
    "bm25f": (False, False),
    "selected": (False, True),
}


def paths(split: str) -> tuple[Path, Path]:
    return BENCHMARK / "data" / split, BENCHMARK / "output" / split


def variants(split: str) -> dict[str, tuple[bool, bool]]:
    return DEV_VARIANTS if split == "dev" else TEST_VARIANTS


def validate_weights(alpha: float, beta: float) -> None:
    if alpha < 0 or beta < 0 or not math.isclose(alpha + beta, 1):
        raise ValueError("alpha and beta must be non-negative and sum to 1")


def run(split: str, alpha: float, beta: float) -> None:
    validate_weights(alpha, beta)
    data_dir, output_dir = paths(split)
    queries_path = data_dir / "queries.tsv"
    queries = read_queries(queries_path)
    runs = {}

    for name, (proximity, semantic) in variants(split).items():
        results, latencies = search_api_results(
            INDEX,
            queries,
            TOP_N,
            use_proximity=proximity,
            use_semantic=semantic,
            alpha=alpha,
            beta=beta,
        )
        runs[name] = {
            "variant": name,
            "top_n": TOP_N,
            "use_proximity": proximity,
            "use_semantic": semantic,
            "latencies_ms": dict(zip(queries, latencies)),
            "results": results,
        }

    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    for name, payload in runs.items():
        (runs_dir / f"{name}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    write_pool(runs, queries, output_dir / "judging_pool.tsv")
    write_manifest(alpha, beta, queries_path, output_dir, variants(split))


def write_pool(runs, queries, path: Path) -> None:
    rows = {}
    for payload in runs.values():
        for query_id, results in payload["results"].items():
            for result in results[:POOL_DEPTH]:
                if not result.get("url"):
                    continue
                rows.setdefault(
                    (int(query_id), str(result["url"])),
                    {
                        "query_id": query_id,
                        "query": queries[int(query_id)],
                        "url": result["url"],
                        "title": result.get("title") or "",
                        "snippet": result.get("snippet") or "",
                    },
                )
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["query_id", "query", "url", "title", "snippet"],
            delimiter="\t",
        )
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))


def file_hash(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_manifest(alpha, beta, queries_path, output_dir, selected_variants) -> None:
    manifest = {
        "alpha": alpha,
        "beta": beta,
        "top_n": TOP_N,
        "pool_depth": POOL_DEPTH,
        "rerank_candidates": RERANK_CANDIDATES,
        "index_sha256": file_hash(INDEX),
        "embeddings_sha256": file_hash(DEFAULT_EMBEDDINGS_PATH),
        "queries_sha256": file_hash(queries_path),
        "variants": {
            name: {"use_proximity": proximity, "use_semantic": semantic}
            for name, (proximity, semantic) in selected_variants.items()
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def score(split: str) -> None:
    data_dir, output_dir = paths(split)
    queries = read_queries(data_dir / "queries.tsv")
    qrels = read_qrels(data_dir / "qrels.tsv")
    rankings, rows = {}, []

    for name in variants(split):
        payload = json.loads(
            (output_dir / "runs" / f"{name}.json").read_text(encoding="utf-8")
        )
        results = {int(query_id): values for query_id, values in payload["results"].items()}
        rankings[name] = results
        rows.append((name, asdict(compute_metrics(
            queries,
            qrels,
            results,
            [float(value) for value in payload["latencies_ms"].values()],
        ))))

    pool_depth = json.loads(
        (output_dir / "manifest.json").read_text(encoding="utf-8")
    )["pool_depth"]
    pool = {
        (query_id, normalize_url(str(result["url"])))
        for results in rankings.values()
        for query_id, query_results in results.items()
        for result in query_results[:pool_depth]
        if result.get("url")
    }
    judged = {
        (query_id, url)
        for query_id, query_qrels in qrels.items()
        for url in query_qrels
    }
    if missing := pool - judged:
        raise ValueError(f"{len(missing)} pooled results have no relevance judgment")

    pairs = (
        (("bm25f", "bm25f-semantic"), ("bm25f-proximity", "full"))
        if split == "dev" else (("bm25f", "selected"),)
    )
    for lexical, semantic in pairs:
        for query_id in queries:
            if {r["url"] for r in rankings[lexical][query_id]} != {
                r["url"] for r in rankings[semantic][query_id]
            }:
                raise ValueError(f"{semantic} changed the candidate set for query {query_id}")

    (output_dir / "metrics.json").write_text(
        json.dumps(dict(rows), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = summary(rows, len(judged), split)
    (output_dir / "README.md").write_text(report, encoding="utf-8")
    print(report)


def summary(rows, judgments, split) -> str:
    metrics = dict(rows)
    selected = "bm25f-semantic" if split == "dev" else "selected"
    table = "\n".join(
        f"| {name} | {values['ndcg_10']:.4f} | {values['ndcg_20']:.4f} | "
        f"{values['mrr_10']:.4f} | {values['positive_10']:.2f} | "
        f"{values['avg_latency_ms']:.2f} |"
        for name, values in rows
    )
    note = (
        "Proximity reduces both nDCG scores.\n\n"
        "These pooled results are for development."
        if split == "dev" else
        "The selected configuration was frozen before this test run."
    )
    return f"""# {split.title()} retrieval evaluation

{metrics["bm25f"]["queries"]} queries, top-100 BM25F candidates, and
{judgments} pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
{table}

Semantic re-ranking gains
{metrics[selected]["ndcg_10"] - metrics["bm25f"]["ndcg_10"]:.4f} nDCG@10 and
{metrics[selected]["ndcg_20"] - metrics["bm25f"]["ndcg_20"]:.4f} nDCG@20.
{note}
"""


def weight_pairs() -> list[tuple[float, float]]:
    return [(alpha / 10, (10 - alpha) / 10) for alpha in range(11)]


def sweep() -> None:
    data_dir, output_dir = paths("dev")
    queries = read_queries(data_dir / "queries.tsv")
    qrels = read_qrels(data_dir / "qrels.tsv")
    rows = []
    for alpha, beta in weight_pairs():
        results, latencies = search_api_results(
            INDEX,
            queries,
            TOP_N,
            use_proximity=False,
            use_semantic=True,
            alpha=alpha,
            beta=beta,
        )
        rows.append({
            "alpha": alpha,
            "beta": beta,
            **asdict(compute_metrics(queries, qrels, results, latencies)),
        })

    output_dir /= "weights"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "metrics.json").write_text(
        json.dumps(rows, indent=2) + "\n",
        encoding="utf-8",
    )
    best = max(rows, key=lambda row: float(row["ndcg_10"] or 0))
    table = "\n".join(
        f"| {row['alpha']:.1f} | {row['beta']:.1f} | "
        f"{row['ndcg_10']:.4f} | {row['ndcg_20']:.4f} |"
        for row in rows
    )
    (output_dir / "README.md").write_text(
        "# Development weight sweep\n\n"
        "| Alpha | Beta | nDCG@10 | nDCG@20 |\n"
        "|---:|---:|---:|---:|\n"
        f"{table}\n\n"
        f"Best nDCG@10: alpha={best['alpha']:.1f}, beta={best['beta']:.1f} "
        f"({best['ndcg_10']:.4f}).\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run")
    run_parser.add_argument("split", choices=("dev", "test"))
    run_parser.add_argument("--alpha", type=float, default=ALPHA)
    run_parser.add_argument("--beta", type=float, default=BETA)
    score_parser = commands.add_parser("score")
    score_parser.add_argument("split", choices=("dev", "test"))
    commands.add_parser("sweep")
    args = parser.parse_args()

    if args.command == "run":
        run(args.split, args.alpha, args.beta)
    elif args.command == "score":
        score(args.split)
    else:
        sweep()


if __name__ == "__main__":
    main()
