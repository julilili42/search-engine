from io import BytesIO

import pytest

import tuebingen_search.data_fetch as data_fetch
from tuebingen_search.data_fetch import _asset_urls, _download, _release_url


def test_release_url_uses_latest_or_tag():
    assert _release_url(None).endswith("/releases/latest")
    assert _release_url("crawl-data-2026-07-13").endswith("/releases/tags/crawl-data-2026-07-13")


def test_asset_urls_requires_crawl_data_assets():
    release = {
        "assets": [
            {"name": "pages.sqlite", "browser_download_url": "https://example.test/pages"},
            {"name": "index.bin", "browser_download_url": "https://example.test/index"},
            {"name": "embeddings.npz", "browser_download_url": "https://example.test/embeddings"},
        ]
    }

    assert _asset_urls(release) == {
        "pages.sqlite": "https://example.test/pages",
        "index.bin": "https://example.test/index",
        "embeddings.npz": "https://example.test/embeddings",
    }

    assert _asset_urls({"assets": release["assets"][:2]}) == {
        "pages.sqlite": "https://example.test/pages",
        "index.bin": "https://example.test/index",
    }

    with pytest.raises(ValueError, match="index.bin"):
        _asset_urls({"assets": release["assets"][:1]})


def test_download_creates_destination_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(data_fetch, "urlopen", lambda _: BytesIO(b"data"))
    destination = tmp_path / "db" / "pages.sqlite"

    _download("https://example.test/pages", destination)

    assert destination.read_bytes() == b"data"
