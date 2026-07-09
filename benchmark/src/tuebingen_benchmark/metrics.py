from __future__ import annotations

import math
from dataclasses import dataclass

from .extract import normalize_url


@dataclass(frozen=True)
class Metrics:
    queries: int
    judged_queries: int
    ndcg_10: float | None
    ndcg_100: float | None
    mrr_10: float | None
    positive_10: float | None
    judged_coverage_10: float | None
    judged_coverage_20: float | None
    avg_latency_ms: float


def dcg(ratings: list[int], k: int) -> float:
    return sum((2**rating - 1) / math.log2(rank + 1) for rank, rating in enumerate(ratings[:k], start=1))


def ndcg(ranked_ratings: list[int], ideal_ratings: list[int], k: int) -> float:
    ideal = dcg(sorted(ideal_ratings, reverse=True), k)
    return 0.0 if ideal == 0 else dcg(ranked_ratings, k) / ideal


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def judged_coverage(results: list[dict[str, object]], qrels: dict[str, int], k: int) -> float:
    cutoff = min(k, len(results))
    if cutoff == 0:
        return 0.0
    judged = sum(
        1
        for result in results[:k]
        if result.get("url") and normalize_url(str(result["url"])) in qrels
    )
    return judged / cutoff


def compute_metrics(
    queries: dict[int, str],
    qrels: dict[int, dict[str, int]],
    results: dict[int, list[dict[str, object]]],
    latencies: list[float],
) -> Metrics:
    ndcg_10: list[float] = []
    ndcg_100: list[float] = []
    mrr_10: list[float] = []
    positive_10: list[float] = []
    coverage_10: list[float] = []
    coverage_20: list[float] = []

    for query_id in queries:
        query_qrels = qrels.get(query_id, {})
        if not query_qrels:
            continue

        query_results = results.get(query_id, [])
        ratings = [
            query_qrels.get(normalize_url(str(result["url"])), 0) if result.get("url") else 0
            for result in query_results
        ]

        ndcg_10.append(ndcg(ratings, list(query_qrels.values()), 10))
        ndcg_100.append(ndcg(ratings, list(query_qrels.values()), 100))
        positive_ranks = [rank for rank, rating in enumerate(ratings[:10], start=1) if rating > 0]
        mrr_10.append(1 / positive_ranks[0] if positive_ranks else 0.0)
        positive_10.append(sum(1 for rating in ratings[:10] if rating > 0))
        coverage_10.append(judged_coverage(query_results, query_qrels, 10))
        coverage_20.append(judged_coverage(query_results, query_qrels, 20))

    return Metrics(
        queries=len(queries),
        judged_queries=sum(1 for query_id in queries if qrels.get(query_id)),
        ndcg_10=mean(ndcg_10),
        ndcg_100=mean(ndcg_100),
        mrr_10=mean(mrr_10),
        positive_10=mean(positive_10),
        judged_coverage_10=mean(coverage_10),
        judged_coverage_20=mean(coverage_20),
        avg_latency_ms=mean(latencies) or 0.0,
    )


def format_metrics(metrics: Metrics) -> str:
    def fmt(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.4f}"

    rows = [
        ("queries", str(metrics.queries)),
        ("judged_queries", str(metrics.judged_queries)),
        ("nDCG@10", fmt(metrics.ndcg_10)),
        ("nDCG@100", fmt(metrics.ndcg_100)),
        ("MRR@10", fmt(metrics.mrr_10)),
        ("positive@10", fmt(metrics.positive_10)),
        ("judged_coverage@10", fmt(metrics.judged_coverage_10)),
        ("judged_coverage@20", fmt(metrics.judged_coverage_20)),
        ("avg_latency_ms", f"{metrics.avg_latency_ms:.2f}"),
    ]
    width = max(len(name) for name, _ in rows)
    return "\n".join(f"{name:<{width}}  {value}" for name, value in rows)


def metric_rows(metrics: dict[str, object]) -> list[tuple[str, float | int | None]]:
    return [
        ("nDCG@10", metrics.get("ndcg_10")),
        ("nDCG@100", metrics.get("ndcg_100")),
        ("MRR@10", metrics.get("mrr_10")),
        ("positive@10", metrics.get("positive_10")),
        ("coverage@10", metrics.get("judged_coverage_10")),
        ("coverage@20", metrics.get("judged_coverage_20")),
        ("latency ms", metrics.get("avg_latency_ms")),
    ]


def format_comparison(left: dict[str, object], right: dict[str, object]) -> str:
    left_metrics = left["metrics"]
    right_metrics = right["metrics"]
    assert isinstance(left_metrics, dict)
    assert isinstance(right_metrics, dict)

    left_name = str(left.get("name") or "left")
    right_name = str(right.get("name") or "right")
    rows = [("metric", left_name, right_name, "delta")]
    for label, left_value in metric_rows(left_metrics):
        right_value = right_metrics.get({
            "nDCG@10": "ndcg_10",
            "nDCG@100": "ndcg_100",
            "MRR@10": "mrr_10",
            "positive@10": "positive_10",
            "coverage@10": "judged_coverage_10",
            "coverage@20": "judged_coverage_20",
            "latency ms": "avg_latency_ms",
        }[label])
        rows.append((label, fmt_value(left_value), fmt_value(right_value), fmt_delta(left_value, right_value)))

    widths = [max(len(str(row[index])) for row in rows) for index in range(4)]
    return "\n".join(
        f"{row[0]:<{widths[0]}}  {row[1]:>{widths[1]}}  {row[2]:>{widths[2]}}  {row[3]:>{widths[3]}}"
        for row in rows
    )


def fmt_value(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def fmt_delta(left: object, right: object) -> str:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return "n/a"
    delta = right - left
    return f"{delta:+.4f}"
