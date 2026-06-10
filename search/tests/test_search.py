# search/tests/test_search.py
import pytest

from tuebingen_search.indexer import index
from tuebingen_search.search import search

PAGES = {
    "apple.html": "<html><body><p>apple apple apple banana</p></body></html>",
    "banana.html": "<html><body><p>banana banana cherry</p></body></html>",
    "cherry.html": "<html><body><p>cherry orange</p></body></html>",
}


@pytest.fixture
def index_path(tmp_path):
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    for name, content in PAGES.items():
        (html_dir / name).write_text(content, encoding="utf-8")

    path = tmp_path / "index.bin"
    index(str(html_dir), str(path))
    return str(path)


def test_search_ranks_by_term_frequency(index_path):
    results = search(index_path, "apple", top_n=10)

    assert len(results) == 1
    assert results[0].rank == 1
    assert results[0].path.endswith("apple.html")
    assert results[0].score > 0


def test_search_returns_all_matching_documents_ranked(index_path):
    results = search(index_path, "banana", top_n=10)

    assert [r.rank for r in results] == [1, 2]
    # banana.html mentions banana twice, apple.html once
    assert results[0].path.endswith("banana.html")
    assert results[1].path.endswith("apple.html")
    assert results[0].score > results[1].score


def test_search_accumulates_scores_over_query_terms(index_path):
    results = search(index_path, "banana cherry", top_n=10)

    paths = [r.path for r in results]
    assert len(results) == 3
    # banana.html matches both terms and ranks first
    assert paths[0].endswith("banana.html")


def test_search_respects_top_n(index_path):
    results = search(index_path, "banana cherry", top_n=1)
    assert len(results) == 1
    assert results[0].rank == 1


def test_search_unknown_term_returns_empty(index_path):
    assert search(index_path, "zucchini", top_n=10) == []


def test_search_empty_query_returns_empty(index_path):
    assert search(index_path, "", top_n=10) == []
    assert search(index_path, "!?.", top_n=10) == []


def test_search_query_is_tokenized_and_deduplicated(index_path):
    once = search(index_path, "apple", top_n=10)
    twice = search(index_path, "Apple, APPLE!", top_n=10)

    assert [(r.path, r.score) for r in twice] == [(r.path, r.score) for r in once]
