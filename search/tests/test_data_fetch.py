import pytest

from tuebingen_search.data_fetch import _asset_urls, _release_url


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
