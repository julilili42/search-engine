import pytest

from tuebingen_search.indexer import index
from helpers import make_page_load
from tuebingen_search.models import Document, Posting, SearchIndex
from tuebingen_search.search import generate_snippet, proximity_bonus, search, search_index

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


def test_search_boosts_nearby_query_terms(tmp_path):
    far_page = tmp_path / "far.html"
    close_page = tmp_path / "close.html"
    index = SearchIndex(
        documents=[
            Document(
                path=far_page,
                url=None,
                length=21,
                terms=("alpha",) + ("x",) * 19 + ("beta",),
            ),
            Document(path=close_page, url=None, length=2, terms=("alpha", "beta")),
        ],
        inverted_index={
            "alpha": [
                Posting(doc_index=0, score=1.0, positions=[0]),
                Posting(doc_index=1, score=1.0, positions=[0]),
            ],
            "beta": [
                Posting(doc_index=0, score=1.0, positions=[20]),
                Posting(doc_index=1, score=1.0, positions=[1]),
            ],
        },
    )

    results = search_index(index, "alpha beta", top_n=2)

    assert results[0].path == close_page
    assert results[0].score > results[1].score


def test_proximity_bonus_requires_all_query_terms():
    assert proximity_bonus({"alpha": [0]}) == 0.0


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


def test_generate_snippet_includes_query_term_with_context():
    terms = ["zero", "one", "two", "target", "three", "four", "five"]

    # "target" is at position 3
    snippet = generate_snippet(terms, {"target": [3]}, context_size=2)

    assert snippet == "... one two target three four ..."


def test_generate_snippet_falls_back_to_start_of_document():
    assert generate_snippet(["one", "two", "three"], {}, context_size=2) == "one two three"


def test_generate_snippet_centers_on_tightest_window():
    terms = ["alpha", "x", "x", "x", "x", "x", "x", "x", "alpha", "beta", "x"]

    # "alpha" appears at 0 and 8, "beta" at 9; snippet should show them together
    snippet = generate_snippet(terms, {"alpha": [0, 8], "beta": [9]}, context_size=1)

    assert snippet == "... x alpha beta ..."


def test_search_does_not_read_the_source_file(tmp_path):
    # the snippet is built from terms stored in the index, so the source file
    # never has to exist at query time
    missing_page = tmp_path / "missing.html"
    index = SearchIndex(
        documents=[Document(path=missing_page, url=None, length=1, terms=("apple",))],
        inverted_index={"apple": [Posting(doc_index=0, score=1.0, positions=[0])]},
    )

    results = search_index(index, "apple", top_n=10)

    assert len(results) == 1
    assert results[0].path == missing_page
    assert results[0].snippet == "apple"


def test_search_index_reports_embedding_score(tmp_path, monkeypatch):
    import sys

    import numpy as np

    search_module = sys.modules["tuebingen_search.search"]

    documents = [
        Document(path=tmp_path / "a.html", url="https://a.test", length=1, terms=("apple",)),
        Document(path=tmp_path / "b.html", url="https://b.test", length=1, terms=("apple",)),
    ]
    index = SearchIndex(
        documents=documents,
        inverted_index={
            "apple": [
                Posting(doc_index=0, score=1.0, positions=[0]),
                Posting(doc_index=1, score=1.0, positions=[0]),
            ]
        },
    )
    doc_embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
    monkeypatch.setattr(search_module, "embed_texts", lambda texts: np.array([[1.0, 0.0]]))

    results = search_index(index, "apple", top_n=10, doc_embeddings=doc_embeddings)

    scores = {result.url: result.embedding_score for result in results}
    assert scores["https://a.test"] == pytest.approx(1.0)
    assert scores["https://b.test"] == pytest.approx(0.0)


def test_search_index_embedding_score_is_none_without_embeddings(tmp_path):
    index = SearchIndex(
        documents=[
            Document(path=tmp_path / "a.html", url="https://a.test", length=1, terms=("apple",))
        ],
        inverted_index={"apple": [Posting(doc_index=0, score=1.0, positions=[0])]},
    )

    results = search_index(index, "apple", top_n=10)

    assert results[0].embedding_score is None


def test_rerank_blends_lexical_and_semantic_scores():
    import numpy as np

    from tuebingen_search.search import rerank

    candidates = [(0, 10.0), (1, 9.9), (2, 5.0)]
    doc_embeddings = np.array(
        [
            [1.0, 0.0],
            [0.0, 1.0],
            [0.7, 0.7],
        ]
    )
    query_embedding = np.array([0.0, 1.0])

    reranked = rerank(candidates, doc_embeddings, query_embedding, alpha=0.5)

    assert [doc_index for doc_index, _, _ in reranked] == [1, 0, 2]
    scores = [score for _, score, _ in reranked]
    assert scores == sorted(scores, reverse=True)
    cosines = dict((doc_index, cosine) for doc_index, _, cosine in reranked)
    assert cosines[1] == pytest.approx(1.0)
    assert cosines[0] == pytest.approx(0.0)
