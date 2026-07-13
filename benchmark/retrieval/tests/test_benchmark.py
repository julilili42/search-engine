import pytest

from tuebingen_benchmark.extract import normalize_url
from tuebingen_benchmark.metrics import dcg, format_comparison, judged_coverage, ndcg
from tuebingen_benchmark.runs import slug


def test_normalize_url_ignores_trailing_slash_and_fragment():
    assert normalize_url("HTTPS://Example.test/a/#part") == "https://example.test/a"


def test_ndcg_is_one_for_ideal_order():
    ratings = [3, 2, 0]

    assert ndcg(ratings, ratings, 10) == pytest.approx(1.0)
    assert dcg([0], 10) == 0.0


def test_judged_coverage_counts_urls_in_qrels():
    results = [{"url": "https://example.test/a/"}, {"url": "https://example.test/b"}]

    assert judged_coverage(results, {"https://example.test/a": 3}, 2) == pytest.approx(0.5)


def test_slug_keeps_run_filenames_simple():
    assert slug("BM25 baseline!") == "bm25-baseline"


def test_format_comparison_shows_delta():
    left = {"name": "a", "metrics": {"ndcg_10": 0.5}}
    right = {"name": "b", "metrics": {"ndcg_10": 0.75}}

    assert "+0.2500" in format_comparison(left, right)
