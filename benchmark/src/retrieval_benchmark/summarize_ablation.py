from __future__ import annotations

import json
from dataclasses import asdict

from retrieval_benchmark.extract import normalize_url, read_qrels, read_queries
from retrieval_benchmark.metrics import compute_metrics
from retrieval_benchmark.paths import DEFAULT_QRELS_PATH, DEFAULT_QUERIES_PATH, OUTPUT_DIR

VARIANTS = ("bm25f", "bm25f-proximity", "bm25f-semantic", "full")


def main() -> None:
    queries = read_queries(DEFAULT_QUERIES_PATH)
    qrels = read_qrels(DEFAULT_QRELS_PATH)
    rows = []
    rankings = {}

    for variant in VARIANTS:
        variant_dir = OUTPUT_DIR / variant
        run = json.loads((variant_dir / "results.json").read_text(encoding="utf-8"))
        results = {int(query_id): values for query_id, values in run["results"].items()}
        rankings[variant] = results
        metrics = compute_metrics(
            queries,
            qrels,
            results,
            [float(value) for value in run["latencies_ms"].values()],
        )
        values = asdict(metrics)
        (variant_dir / "metrics.json").write_text(
            json.dumps(values, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (variant_dir / "README.md").write_text(
            readme(variant, run, values),
            encoding="utf-8",
        )
        rows.append((variant, values))

    pool_depth = json.loads(
        (OUTPUT_DIR / "manifest.json").read_text(encoding="utf-8")
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
    if judged != pool:
        raise ValueError("data/qrels.tsv does not exactly match the current result pool")

    for lexical, semantic in (
        ("bm25f", "bm25f-semantic"),
        ("bm25f-proximity", "full"),
    ):
        for query_id in queries:
            lexical_urls = {result["url"] for result in rankings[lexical][query_id]}
            semantic_urls = {result["url"] for result in rankings[semantic][query_id]}
            if semantic_urls != lexical_urls:
                raise ValueError(
                    f"{semantic} changed the candidate set for query {query_id}"
                )

    (OUTPUT_DIR / "README.md").write_text(summary(rows), encoding="utf-8")


def readme(variant: str, run: dict[str, object], metrics: dict[str, object]) -> str:
    return f"""# {variant}

- Proximity: `{str(run["use_proximity"]).lower()}`
- Semantic re-ranking: `{str(run["use_semantic"]).lower()}`
- Candidates/results: BM25F top 100 / top 100
- Queries judged: {metrics["judged_queries"]}/{metrics["queries"]}
- nDCG@10: {metrics["ndcg_10"]:.4f}
- nDCG@20: {metrics["ndcg_20"]:.4f}
- MRR@10: {metrics["mrr_10"]:.4f}
- Positive results@10: {metrics["positive_10"]:.2f}
- Judged coverage@20: {metrics["judged_coverage_20"]:.4f}
- Mean warmed API latency: {metrics["avg_latency_ms"]:.2f} ms

`results.json` contains the complete ranking and per-query latency;
`metrics.json` contains the machine-readable aggregate metrics.
"""


def summary(rows: list[tuple[str, dict[str, object]]]) -> str:
    metrics = dict(rows)
    ndcg_10_gain = metrics["bm25f-semantic"]["ndcg_10"] - metrics["bm25f"]["ndcg_10"]
    ndcg_20_gain = metrics["bm25f-semantic"]["ndcg_20"] - metrics["bm25f"]["ndcg_20"]
    table = [
        "| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for variant, metrics in rows:
        table.append(
            f"| {variant} | {metrics['ndcg_10']:.4f} | {metrics['ndcg_20']:.4f} | "
            f"{metrics['mrr_10']:.4f} | {metrics['positive_10']:.2f} | "
            f"{metrics['avg_latency_ms']:.2f} |"
        )
    return f"""# Retrieval ablation

All variants use the same 20 queries, top-100 BM25F candidates, and 466 pooled
top-20 judgments.

{chr(10).join(table)}

Semantic re-ranking without proximity performs best, adding
{ndcg_10_gain:.4f} nDCG@10 and {ndcg_20_gain:.4f} nDCG@20 over BM25F.
Proximity reduces both nDCG scores.

Judgments are single-assessor Codex ratings from retrieved metadata. These
pooled results are diagnostic, not an unbiased generalization estimate.
"""


if __name__ == "__main__":
    main()
