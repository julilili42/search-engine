# search/tests/test_api.py
import pytest
from fastapi.testclient import TestClient

from tuebingen_search.api import app
from tuebingen_search.indexer import index

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
    index(str(tmp_path / "html"), str(index_path))

    monkeypatch.setenv("INDEX_PATH", str(index_path))
    with TestClient(app) as client:
        yield client


def test_search_returns_ranked_results(client):
    response = client.get("/search", params={"q": "banana"})

    assert response.status_code == 200
    results = response.json()
    assert [r["rank"] for r in results] == [1, 2]
    assert results[0]["path"].endswith("banana.html")
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


def test_health_reports_document_count(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["documents"] == len(PAGES)
