from pathlib import Path
from urllib.robotparser import RobotFileParser

import httpx
import pytest

from tuebingen_crawler.crawler import crawl_site, evaluate_links
from tuebingen_crawler.models import CrawlSite, CrawlState
from tuebingen_crawler.save_pages import PageStore

HTML_HEADERS = {"Content-Type": "text/html; charset=utf-8"}

# Englischer, Tübingen-relevanter Fülltext, damit die Heuristik die Seiten
# als keep-würdig einstuft (sonst werden sie als off-topic/non-en verworfen).
FILLER = (
    "<html lang=\"en\"><title>Tübingen</title>"
    "The city of Tübingen is an old university town in the south of Germany "
    "and it is a place that you can visit for the old streets and the river. "
)


def page(*links: str) -> bytes:
    return (FILLER + "".join(links)).encode("utf-8")


PAGES = {
    "/": page(
        '<a href="/a">Tübingen A</a>',
        '<a href="/b">Tübingen B</a>',
        '<a href="https://example.com/x">ext</a>',
    ),
    "/a": page('<a href="/b">Tübingen B</a>', '<a href="/c">Tübingen C</a>'),
    "/b": page("leaf b"),
    "/c": page("leaf c"),
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
        max_pages_per_seed=100,
        request_timeout=1.0,
        retry_delay=0.0,
        request_delay=0.0,
        retries=1,
    )
    defaults.update(overrides)
    return CrawlSite(**defaults)


def run_crawl(
    client,
    tmp_path,
    page_store,
    seen_urls=None,
    host_counts=None,
    max_pages_per_host=None,
    **site_overrides,
):
    return crawl_site(
        client=client,
        site=make_site(**site_overrides),
        save_dir=tmp_path,
        save_state_every=10,
        page_store=page_store,
        robot_parser=allow_all_robots(),
        user_agent="TestCrawler/1.0",
        seen_urls=seen_urls,
        host_counts=host_counts,
        max_pages_per_host=max_pages_per_host,
    )


def stored_urls(page_store) -> list[str]:
    return sorted(page.url for page in page_store.iter_html_pages())


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

    for page in page_store.iter_html_pages():
        saved = Path(page.path)
        assert saved.exists()
        assert saved.read_bytes() == PAGES[httpx.URL(page.url).path]


def test_crawl_site_uses_normalized_host_for_storage(tmp_path, page_store):
    with make_client(PAGES, []) as client:
        run_crawl(client, tmp_path, page_store, url="https://www.host/")

    pages = list(page_store.iter_html_pages())
    assert pages
    assert {page.host for page in pages} == {"host"}
    assert all(Path(page.path).parent == tmp_path / "host" for page in pages)


def test_crawl_site_respects_max_pages_per_seed(client, tmp_path, page_store, requested_paths):
    run_crawl(client, tmp_path, page_store, max_pages_per_seed=2)

    assert len(stored_urls(page_store)) == 2
    assert len(requested_paths) == 2


def test_crawl_site_skips_fetching_when_host_capped(client, tmp_path, page_store, requested_paths):
    host_counts = {"host": 1}
    state = run_crawl(
        client, tmp_path, page_store, host_counts=host_counts, max_pages_per_host=1
    )

    assert stored_urls(page_store) == []
    assert state.statistics.saved == 0
    assert host_counts["host"] == 1
    assert requested_paths == []


def test_crawl_site_cap_counts_saved_pages_per_host(client, tmp_path, page_store):
    host_counts: dict[str, int] = {}
    run_crawl(
        client, tmp_path, page_store, host_counts=host_counts, max_pages_per_host=2
    )

    assert len(stored_urls(page_store)) == 2
    assert host_counts == {"host": 2}
    assert "https://host/c" not in stored_urls(page_store)


def test_evaluate_links_skips_enqueue_for_capped_host():
    state = CrawlState()
    host_counts = {"host": 5}
    evaluate_links(
        state=state,
        links=[("/a", "Tübingen")],
        current_url="https://host/",
        depth=0,
        parent_relevance=5.0,
        parent_host="host",
        host_counts=host_counts,
        max_pages_per_host=5,
    )

    assert state.frontier == []
    assert "https://host/a" in state.seen_urls


def test_evaluate_links_enqueues_below_cap():
    state = CrawlState()
    host_counts = {"host": 1}
    evaluate_links(
        state=state,
        links=[("/a", "Tübingen")],
        current_url="https://host/",
        depth=0,
        parent_relevance=5.0,
        parent_host="host",
        host_counts=host_counts,
        max_pages_per_host=5,
    )

    assert len(state.frontier) == 1
    assert "https://host/a" in state.seen_urls


def test_crawl_site_updates_statistics(client, tmp_path, page_store):
    state = run_crawl(client, tmp_path, page_store)

    assert state.statistics.fetched == 4
    assert state.statistics.saved == 4
    assert state.statistics.discovered == 4
    assert state.statistics.failed == 0


def test_crawl_site_counts_failed_fetches(tmp_path, page_store, requested_paths):
    # /missing returns 404 and exhausts its single retry
    pages = {
        "/": page('<a href="/a">Tübingen A</a>', '<a href="/missing">Tübingen dead</a>'),
        "/a": page("leaf"),
    }

    with make_client(pages, requested_paths) as client:
        state = run_crawl(client, tmp_path, page_store)

    assert "https://host/missing" not in stored_urls(page_store)
    assert stored_urls(page_store) == ["https://host/", "https://host/a"]
    assert state.statistics.failed == 1
    assert state.statistics.saved == 2


def test_crawl_site_skips_request_errors(tmp_path, page_store):
    def handler(request):
        raise httpx.ConnectError("certificate verify failed", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        state = run_crawl(client, tmp_path, page_store)

    assert stored_urls(page_store) == []
    assert state.statistics.failed == 1
    assert state.statistics.saved == 0


def test_crawl_site_resumes_completed_state_without_fetching(client, tmp_path, page_store, requested_paths):
    first = run_crawl(client, tmp_path, page_store)
    fetches_first_run = len(requested_paths)

    second = run_crawl(client, tmp_path, page_store)

    assert second.frontier == first.frontier
    # state was complete, so the second run performs no requests
    assert len(requested_paths) == fetches_first_run


def test_crawl_site_rejects_invalid_starting_url(client, tmp_path, page_store):
    with pytest.raises(ValueError):
        run_crawl(client, tmp_path, page_store, url="ftp://host/")


def test_shared_seen_prevents_refetch_across_seeds(client, tmp_path, page_store, requested_paths):
    # ein gemeinsames seen-Set über zwei Crawl-Läufe hinweg; getrennte save_dirs,
    # damit der zweite Lauf NICHT über den persistierten State resumt und so
    # wirklich nur der Effekt des geteilten seen-Sets getestet wird.
    seen_urls: set[str] = set()

    run_crawl(client, tmp_path / "seed_a", page_store, seen_urls=seen_urls)
    first_run_paths = list(requested_paths)
    requested_paths.clear()

    # zweiter Seed mit eigenem State, aber demselben seen. Nur der Seed-Root
    # wird immer neu in die Frontier gepusht; die entdeckten Kinder-Links
    # (/a, /b, /c) sind bereits im geteilten seen und werden nicht erneut geholt.
    run_crawl(client, tmp_path / "seed_b", page_store, seen_urls=seen_urls)

    assert sorted(first_run_paths) == ["/", "/a", "/b", "/c"]
    assert requested_paths == ["/"]  # nur der Root, keine Kinder-Refetches
