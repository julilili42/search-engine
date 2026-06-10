import pytest

from tuebingen_crawler.urls import (
    canonical_url,
    extract_urls,
    hostname_for_url,
    url_slug,
)


def test_canonical_url_removes_query_and_fragment():
    url, ok = canonical_url(
        "/wiki/Tübingen?x=1#top",
        "https://www.tuepedia.de/",
        "www.tuepedia.de",
    )
    assert ok
    assert url == "https://www.tuepedia.de/wiki/Tübingen"

def test_canonical_url_rejects_other_hosts():
    url, ok = canonical_url(
        "https://example.com/page",
        "https://www.tuepedia.de/",
        "www.tuepedia.de",
    )
    assert not ok
    assert url == ""

def test_canonical_url_resolves_relative_paths():
    url, ok = canonical_url(
        "subpage",
        "https://www.tuepedia.de/wiki/",
        "www.tuepedia.de",
    )
    assert ok
    assert url == "https://www.tuepedia.de/wiki/subpage"

def test_canonical_url_strips_trailing_slash_except_root():
    url, ok = canonical_url(
        "/wiki/Tübingen/",
        "https://www.tuepedia.de/",
        "www.tuepedia.de",
    )
    assert ok
    assert url == "https://www.tuepedia.de/wiki/Tübingen"

    root, ok = canonical_url(
        "https://www.tuepedia.de/",
        "https://www.tuepedia.de/",
        "www.tuepedia.de",
    )
    assert ok
    assert root == "https://www.tuepedia.de/"

def test_canonical_url_lowercases_netloc():
    url, ok = canonical_url(
        "https://WWW.Tuepedia.DE/wiki/page",
        "https://www.tuepedia.de/",
        "www.tuepedia.de",
    )
    assert ok
    assert url == "https://www.tuepedia.de/wiki/page"

@pytest.mark.parametrize("href", [
    "mailto:someone@example.com",
    "javascript:void(0)",
    "ftp://www.tuepedia.de/file",
])
def test_canonical_url_rejects_non_http_schemes(href):
    url, ok = canonical_url(href, "https://www.tuepedia.de/", "www.tuepedia.de")
    assert not ok
    assert url == ""


def test_hostname_for_url_lowercases_host():
    assert hostname_for_url("https://WWW.Tuepedia.DE/wiki") == "www.tuepedia.de"

def test_hostname_for_url_rejects_missing_scheme():
    with pytest.raises(ValueError):
        hostname_for_url("www.tuepedia.de/wiki")

def test_hostname_for_url_rejects_unsupported_scheme():
    with pytest.raises(ValueError):
        hostname_for_url("ftp://www.tuepedia.de/")


def test_extract_urls_finds_anchor_links():
    body = b'<html><body><a href="/wiki/a">A</a><a href="/wiki/b">B</a></body></html>'
    seen = {}
    urls = extract_urls(seen, body, "https://www.tuepedia.de/", "www.tuepedia.de")
    assert urls == [
        "https://www.tuepedia.de/wiki/a",
        "https://www.tuepedia.de/wiki/b",
    ]
    assert all(seen[url] for url in urls)

def test_extract_urls_skips_seen_and_duplicate_links():
    body = b'<a href="/wiki/a">A</a><a href="/wiki/a#section">A again</a><a href="/wiki/b">B</a>'
    seen = {"https://www.tuepedia.de/wiki/b": True}
    urls = extract_urls(seen, body, "https://www.tuepedia.de/", "www.tuepedia.de")
    assert urls == ["https://www.tuepedia.de/wiki/a"]

def test_extract_urls_skips_foreign_hosts_and_non_anchor_tags():
    body = (
        b'<a href="https://example.com/x">external</a>'
        b'<link href="/style.css">'
        b'<a name="no-href">anchor without href</a>'
    )
    urls = extract_urls({}, body, "https://www.tuepedia.de/", "www.tuepedia.de")
    assert urls == []

def test_extract_urls_handles_invalid_utf8():
    body = b'<a href="/wiki/a">\xff\xfe broken bytes</a>'
    urls = extract_urls({}, body, "https://www.tuepedia.de/", "www.tuepedia.de")
    assert urls == ["https://www.tuepedia.de/wiki/a"]


def test_url_slug_basic_path():
    assert url_slug("https://www.tuepedia.de/wiki/Tübingen") == "wiki-tübingen"

def test_url_slug_root_becomes_index():
    assert url_slug("https://www.tuepedia.de/") == "index"

def test_url_slug_includes_query():
    slug = url_slug("https://host/search?q=test&page=2")
    assert slug == "search-q-test-page-2"

def test_url_slug_truncates_long_paths():
    slug = url_slug("https://host/" + "a" * 200)
    assert len(slug) <= 90

def test_url_slug_never_empty():
    assert url_slug("https://host/---") == "page"
