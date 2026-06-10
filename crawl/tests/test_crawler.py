import json
from pathlib import Path

import httpx
import pytest

from tuebingen_crawler.crawler import crawl_site, save_jsonl
from tuebingen_crawler.models import CrawlSite, Statistics

HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8"}

PAGES = {
    "/": b'<a href="/a">A</a><a href="/b">B</a><a href="https://example.com/x">ext</a>',
    "/a": b'<a href="/b">B</a><a href="/c">C</a>',
    "/b": b"<html>leaf</html>",
    "/c": b"<html>leaf</html>",
}


@pytest.fixture
def requested_paths():
    return []


def make_client(pages, requested_paths) -> httpx.Client:
    def handler(request):
        requested_paths.append(request.url.path)
        body = pages.get(request.url.path)
        if body is None:
            return httpx.Response(404, headers=HTML_HEADERS)
        return httpx.Response(200, headers=HTML_HEADERS, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def client(requested_paths):
    with make_client(PAGES, requested_paths) as client:
        yield client


def make_site(**overrides) -> CrawlSite:
    defaults = dict(
        url="https://host/",
        max_pages=100,
        request_timeout=1.0,
        retry_delay=0.0,
        request_delay=0.0,
        retries=1,
    )
    defaults.update(overrides)
    return CrawlSite(**defaults)


def run_crawl(client, tmp_path, statistics=None, **site_overrides):
    return crawl_site(
        client=client,
        site=make_site(**site_overrides),
        seen_urls={},
        save_dir=str(tmp_path),
        save_state_every=10,
        statistics=statistics or Statistics(),
    )


def test_crawl_site_visits_all_reachable_pages(client, tmp_path, requested_paths):
    index = run_crawl(client, tmp_path)

    assert sorted(index) == [
        "https://host/",
        "https://host/a",
        "https://host/b",
        "https://host/c",
    ]
    # every page is fetched exactly once
    assert sorted(requested_paths) == ["/", "/a", "/b", "/c"]


def test_crawl_site_saves_html_files(client, tmp_path):
    index = run_crawl(client, tmp_path)

    for url, path in index.items():
        saved = Path(path)
        assert saved.exists()
        assert saved.read_bytes() == PAGES[httpx.URL(url).path]


def test_crawl_site_respects_max_pages(client, tmp_path, requested_paths):
    index = run_crawl(client, tmp_path, max_pages=2)

    assert len(index) == 2
    assert len(requested_paths) == 2


def test_crawl_site_updates_statistics(client, tmp_path):
    statistics = Statistics()
    run_crawl(client, tmp_path, statistics=statistics)

    assert statistics.fetched == 4
    assert statistics.saved == 4
    assert statistics.discovered == 4
    assert statistics.failed == 0


def test_crawl_site_counts_failed_fetches(tmp_path, requested_paths):
    # /missing returns 404 and exhausts its single retry
    pages = {
        "/": b'<a href="/a">A</a><a href="/missing">dead</a>',
        "/a": b"<html>leaf</html>",
    }
    statistics = Statistics()

    with make_client(pages, requested_paths) as client:
        index = run_crawl(client, tmp_path, statistics=statistics)

    assert "https://host/missing" not in index
    assert sorted(index) == ["https://host/", "https://host/a"]
    assert statistics.failed == 1
    assert statistics.saved == 2


def test_crawl_site_resumes_completed_state_without_fetching(client, tmp_path, requested_paths):
    first_index = run_crawl(client, tmp_path)
    fetches_first_run = len(requested_paths)

    second_index = run_crawl(client, tmp_path)

    assert second_index == first_index
    # state was complete, so the second run performs no requests
    assert len(requested_paths) == fetches_first_run


def test_crawl_site_rejects_invalid_starting_url(client, tmp_path):
    with pytest.raises(ValueError):
        run_crawl(client, tmp_path, url="ftp://host/")


def test_save_jsonl_writes_one_row_per_page(tmp_path):
    index = {
        "https://host/": {
            "https://host/": "/data/host/index.html",
            "https://host/a": "/data/host/a.html",
        },
        "https://other/": {
            "https://other/x": "/data/other/x.html",
        },
    }
    out = tmp_path / "out" / "index.jsonl"

    save_jsonl(out, index)

    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 3
    assert rows[0] == {
        "site": "https://host/",
        "url": "https://host/",
        "path": "/data/host/index.html",
    }
    assert {row["site"] for row in rows} == {"https://host/", "https://other/"}
