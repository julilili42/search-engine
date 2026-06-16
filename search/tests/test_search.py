import pytest

from tuebingen_search.indexer import index
from helpers import make_page_load
from tuebingen_search.models import Document, Posting, SearchIndex
from tuebingen_search.search import generate_snippet, search, search_index

PAGES = {
    "apple.html": "<html><body><p>apple apple apple banana</p></body></html>",
    "banana.html": "<html><body><p>banana banana cherry</p></body></html>",
    "cherry.html": "<html><body><p>cherry orange</p></body></html>",
}

@pytest.fixture
def index_path(tmp_path):
    html_dir = tmp_path / "html"
    site_dir = html_dir / "site"
    site_dir.mkdir(parents=True)
    for name, content in PAGES.items():
        (site_dir / name).write_text(content, encoding="utf-8")

    path = tmp_path / "index.bin"
    pages = {site_dir / name: "text/html; charset=utf-8" for name in PAGES}
    index(path, make_page_load(tmp_path / "pages.sqlite", pages))
    return str(path)


def test_search_ranks_by_term_frequency(index_path):
    results = search(index_path, "apple", top_n=10)

    assert len(results) == 1
    assert results[0].rank == 1
    assert str(results[0].path).endswith("apple.html")
    assert results[0].score > 0


def test_search_returns_all_matching_documents_ranked(index_path):
    results = search(index_path, "banana", top_n=10)

    assert [r.rank for r in results] == [1, 2]
    # banana.html mentions banana twice, apple.html once
    assert str(results[0].path).endswith("banana.html")
    assert str(results[1].path).endswith("apple.html")
    assert results[0].score > results[1].score


def test_search_accumulates_scores_over_query_terms(index_path):
    results = search(index_path, "banana cherry", top_n=10)

    paths = [str(r.path) for r in results]
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


def test_generate_snippet_includes_query_term_with_context(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        "<html><body><p>zero one two target three four five</p></body></html>",
        encoding="utf-8",
    )

    snippet = generate_snippet(page, {"target"}, context_size=2)

    assert snippet == "... one two target three four ..."


def test_generate_snippet_falls_back_to_start_of_document(tmp_path):
    page = tmp_path / "page.html"
    page.write_text(
        "<html><body><p>one two three</p></body></html>",
        encoding="utf-8",
    )

    assert generate_snippet(page, {"missing"}, context_size=2) == "one two three"


def test_search_returns_result_when_snippet_source_is_missing(tmp_path):
    missing_page = tmp_path / "missing.html"
    index = SearchIndex(
        documents=[Document(path=missing_page, url=None, length=1)],
        inverted_index={"apple": [Posting(doc_index=0, score=1.0)]},
    )

    results = search_index(index, "apple", top_n=10)

    assert len(results) == 1
    assert results[0].path == missing_page
    assert results[0].snippet == ""
