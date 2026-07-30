import pytest

from retrieval_benchmark.extract import normalize_url, read_qrels, read_queries
from retrieval_benchmark.metrics import dcg, judged_coverage, ndcg
from retrieval_benchmark.cli import reweight_results, weight_pairs


def test_normalize_url_ignores_trailing_slash_and_fragment():
    assert normalize_url("HTTPS://Example.test/a/#part") == "https://example.test/a"


def test_ndcg_is_one_for_ideal_order():
    ratings = [3, 2, 0]

    assert ndcg(ratings, ratings, 10) == pytest.approx(1.0)
    assert dcg([0], 10) == 0.0


def test_judged_coverage_counts_urls_in_qrels():
    results = [{"url": "https://example.test/a/"}, {"url": "https://example.test/b"}]

    assert judged_coverage(results, {"https://example.test/a": 3}, 2) == pytest.approx(0.5)


def test_input_files_reject_ambiguous_data(tmp_path):
    queries = tmp_path / "queries.tsv"
    queries.write_text("1\tfirst\n1\tsecond\n", encoding="utf-8")
    qrels = tmp_path / "qrels.tsv"
    qrels.write_text("1\thttps://example.test\t4\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate query ID"):
        read_queries(queries)
    with pytest.raises(ValueError, match="Invalid rating"):
        read_qrels(qrels)


def test_weight_sweep_covers_all_tenths():
    pairs = weight_pairs()

    assert len(pairs) == 11
    assert pairs[0] == (0.0, 1.0)
    assert pairs[-1] == (1.0, 0.0)
    assert all(alpha + beta == pytest.approx(1.0) for alpha, beta in pairs)


def test_reweight_results_uses_archived_lexical_and_semantic_scores():
    lexical = {
        1: [
            {"path": "lexical", "score": 2.0},
            {"path": "semantic", "score": 1.0},
        ]
    }
    semantic = {
        1: [
            {"path": "semantic", "embedding_score": 0.9},
            {"path": "lexical", "embedding_score": 0.1},
        ]
    }

    assert reweight_results(lexical, semantic, 1.0, 0.0)[1][0]["path"] == "lexical"
    assert reweight_results(lexical, semantic, 0.0, 1.0)[1][0]["path"] == "semantic"
