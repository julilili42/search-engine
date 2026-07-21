import pytest
from fastapi.testclient import TestClient

from tuebingen_search.api import app
from tuebingen_search.indexer import index
from helpers import make_page_load

PAGES = {
    "apple.html": "<html><body><p>apple apple apple banana</p></body></html>",
    "banana.html": "<html><body><p>banana banana cherry</p></body></html>",
    "cherry.html": "<html><body><p>cherry orange</p></body></html>",
}

@pytest.fixture
def client(tmp_path, monkeypatch):
    site_dir = tmp_path / "html" / "site"
    site_dir.mkdir(parents=True)
    for name, content in PAGES.items():
        (site_dir / name).write_text(content, encoding="utf-8")

    index_path = tmp_path / "index.bin"
    pages = {site_dir / name: "text/html; charset=utf-8" for name in PAGES}
    index(index_path, make_page_load(tmp_path / "pages.sqlite", pages))

    monkeypatch.setenv("INDEX_PATH", str(index_path))
    with TestClient(app) as client:
        yield client


def test_search_returns_ranked_results(client):
    response = client.get("/search", params={"q": "banana"})

    assert response.status_code == 200
    results = response.json()
    assert [r["rank"] for r in results] == [1, 2]
    assert results[0]["path"].endswith("banana.html")
    assert results[0]["title"] == "banana"
    assert results[0]["score"] > results[1]["score"]


def test_search_respects_top_n(client):
    results = client.get("/search", params={"q": "banana cherry", "top_n": 1}).json()
    assert len(results) == 1


def test_search_unknown_term_returns_empty(client):
    assert client.get("/search", params={"q": "zucchini"}).json() == []


def test_search_requires_query(client):
    assert client.get("/search").status_code == 422


def test_search_rejects_invalid_top_n(client):
    assert client.get("/search", params={"q": "apple", "top_n": 0}).status_code == 422
    assert client.get("/search", params={"q": "apple", "top_n": 101}).status_code == 422


def test_search_accepts_custom_category_axes(client, monkeypatch):
    import sys

    import numpy as np

    search_module = sys.modules["tuebingen_search.search"]

    def fake_embed(texts):
        # 1 text -> query embedding, 2 texts -> a pair of category axes
        return np.array([[1.0, 0.0]]) if len(texts) == 1 else np.array([[0.0, 1.0], [1.0, 0.0]])

    monkeypatch.setattr("tuebingen_search.api.embed_texts", fake_embed)
    monkeypatch.setattr(search_module, "embed_texts", fake_embed)
    client.app.state.doc_embeddings = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
    client.app.state.category_axes = np.array([[1.0, 0.0], [0.0, 1.0]])

    default_results = client.get("/search", params={"q": "banana cherry"}).json()
    custom_results = client.get(
        "/search", params={"q": "banana cherry", "cat_x": "custom x", "cat_y": "custom y"}
    ).json()

    default_coords = {r["path"]: (r["embedding_x"], r["embedding_y"]) for r in default_results}
    custom_coords = {r["path"]: (r["embedding_x"], r["embedding_y"]) for r in custom_results}
    assert default_coords != custom_coords


def test_health_reports_document_count(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["documents"] == len(PAGES)
