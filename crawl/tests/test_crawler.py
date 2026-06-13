from pathlib import Path
from urllib.robotparser import RobotFileParser

import httpx
import pytest

from tuebingen_crawler.crawler import crawl_site
from tuebingen_crawler.models import CrawlSite
from tuebingen_crawler.page_store import PageStore

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


@pytest.fixture
def page_store(tmp_path):
    with PageStore(tmp_path / "pages.sqlite") as store:
        yield store


def allow_all_robots() -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse([])  # empty rules => everything is allowed
    return parser


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


def run_crawl(client, tmp_path, page_store, **site_overrides):
    return crawl_site(
        client=client,
        site=make_site(**site_overrides),
        save_dir=tmp_path,
        save_state_every=10,
        page_store=page_store,
        robot_parser=allow_all_robots(),
        user_agent="TestCrawler/1.0",
    )


def stored_urls(page_store) -> list[str]:
    return sorted(page.url for page in page_store.iter_pages())


def test_crawl_site_visits_all_reachable_pages(client, tmp_path, page_store, requested_paths):
    run_crawl(client, tmp_path, page_store)

    assert stored_urls(page_store) == [
        "https://host/",
        "https://host/a",
        "https://host/b",
        "https://host/c",
    ]
    # every page is fetched exactly once
    assert sorted(requested_paths) == ["/", "/a", "/b", "/c"]


def test_crawl_site_saves_html_files(client, tmp_path, page_store):
    run_crawl(client, tmp_path, page_store)

    for page in page_store.iter_pages():
        saved = Path(page.path)
        assert saved.exists()
        assert saved.read_bytes() == PAGES[httpx.URL(page.url).path]


def test_crawl_site_respects_max_pages(client, tmp_path, page_store, requested_paths):
    run_crawl(client, tmp_path, page_store, max_pages=2)

    assert len(stored_urls(page_store)) == 2
    assert len(requested_paths) == 2


def test_crawl_site_updates_statistics(client, tmp_path, page_store):
    state = run_crawl(client, tmp_path, page_store)

    assert state.statistics.fetched == 4
    assert state.statistics.saved == 4
    assert state.statistics.discovered == 4
    assert state.statistics.failed == 0


def test_crawl_site_counts_failed_fetches(tmp_path, page_store, requested_paths):
    # /missing returns 404 and exhausts its single retry
    pages = {
        "/": b'<a href="/a">A</a><a href="/missing">dead</a>',
        "/a": b"<html>leaf</html>",
    }

    with make_client(pages, requested_paths) as client:
        state = run_crawl(client, tmp_path, page_store)

    assert "https://host/missing" not in stored_urls(page_store)
    assert stored_urls(page_store) == ["https://host/", "https://host/a"]
    assert state.statistics.failed == 1
    assert state.statistics.saved == 2


def test_crawl_site_resumes_completed_state_without_fetching(client, tmp_path, page_store, requested_paths):
    first = run_crawl(client, tmp_path, page_store)
    fetches_first_run = len(requested_paths)

    second = run_crawl(client, tmp_path, page_store)

    assert second.queue == first.queue
    # state was complete, so the second run performs no requests
    assert len(requested_paths) == fetches_first_run


def test_crawl_site_rejects_invalid_starting_url(client, tmp_path, page_store):
    with pytest.raises(ValueError):
        run_crawl(client, tmp_path, page_store, url="ftp://host/")
