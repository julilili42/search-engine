import math
from pathlib import Path
from urllib.robotparser import RobotFileParser

import httpx
import pytest

import tuebingen_crawler.scheduler as scheduler_module
from tuebingen_crawler.crawler import CrawlContext, process_lease
from tuebingen_crawler.frontier import (
    GlobalFrontier,
    HOST_REJECT_CUTOFF,
    LINK_SCORE_WEIGHT,
)
from tuebingen_crawler.scheduler import crawl_hostname
from tuebingen_crawler.link_evaluation import evaluate_links as _evaluate_links
from tuebingen_crawler.link_classifier import classify_link
from tuebingen_crawler.models import Config, CrawlSite, CrawlState
from tuebingen_crawler.save_pages import LinkStore, PageStore
from tuebingen_crawler.storage import RobotsCache
from tuebingen_crawler.urls import validate_start_url
from verdict_ml.base import VerdictPrediction

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


class FakePagePredictor:
    def predict(self, example):
        return VerdictPrediction(
            label="positive",
            positive_probability=0.91,
            model_path=Path("fake_page_verdict.joblib"),
        )


class FakeLinkPredictor:
    # with no fixed probability, mimics the crawl intent: Tübingen links score high
    def __init__(self, probability: float | None = None) -> None:
        self.probability = probability

    def predict(self, example):
        prob = self.probability
        if prob is None:
            text = f"{example.anchor} {example.target_url}".lower()
            # junk scores below the enqueue floor, on-topic links well above
            prob = 0.9 if ("tübingen" in text or "tuebingen" in text) else 0.01
        return VerdictPrediction(
            label="positive" if prob >= 0.5 else "negative",
            positive_probability=prob,
            model_path=Path("fake_link_verdict.joblib"),
        )


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


@pytest.fixture
def link_store(tmp_path):
    with LinkStore(tmp_path / "pages.sqlite") as store:
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


def evaluate_links(*, state, host_counts, **kwargs):
    frontier = kwargs.pop(
        "frontier",
        GlobalFrontier(
            state,
            request_delays={0: 0.0},
            max_pages_per_seed={0: None},
            max_discovered_per_seed={0: None},
            saved_urls_by_host=host_counts,
        ),
    )
    _evaluate_links(
        state=state,
        host_counts=host_counts,
        frontier=frontier,
        seed_index=0,
        **kwargs,
    )
    frontier.snapshot()


def run_crawl(
    client,
    tmp_path,
    page_store,
    link_store=None,
    seen_urls=None,
    host_counts=None,
    host_reject_counts=None,
    max_pages_per_host=None,
    page_critic=None,
    link_critic=None,
    robots=None,
    **site_overrides,
):
    page_critic = page_critic or FakePagePredictor()
    link_critic = link_critic or FakeLinkPredictor()
    if link_store is None:
        with LinkStore(tmp_path / "pages.sqlite") as generated_link_store:
            return run_crawl(
                client,
                tmp_path,
                page_store,
                link_store=generated_link_store,
                seen_urls=seen_urls,
                host_counts=host_counts,
                host_reject_counts=host_reject_counts,
                max_pages_per_host=max_pages_per_host,
                page_critic=page_critic,
                link_critic=link_critic,
                robots=robots,
                **site_overrides,
            )

    site = make_site(**site_overrides)
    state = CrawlState(seen_urls=seen_urls if seen_urls is not None else set())
    host_counts = host_counts if host_counts is not None else {}
    host_reject_counts = host_reject_counts if host_reject_counts is not None else {}
    frontier = GlobalFrontier(
        state,
        request_delays={0: site.request_delay},
        max_pages_per_seed={0: site.max_pages_per_seed},
        max_discovered_per_seed={0: site.max_discovered_per_seed},
        saved_urls_by_host=host_counts,
    )
    frontier.submit(1_000_000.0, validate_start_url(site.url), 0, 0, seed=True)
    context = CrawlContext(
        client=client,
        state=state,
        page_store=page_store,
        link_store=link_store,
        robots=robots or allow_all_robots(),
        user_agent="TestCrawler/1.0",
        save_dir=tmp_path,
        host_counts=host_counts,
        host_reject_counts=host_reject_counts,
        max_pages_per_host=max_pages_per_host,
        page_critic=page_critic,
        link_critic=link_critic,
    )
    while (lease := frontier.claim()) is not None:
        process_lease(context, site, frontier, lease)
    return state


def stored_urls(page_store) -> list[str]:
    return sorted(page.url for page in page_store.iter_html_pages())


def rejected_records(page_store):
    return {page.url: page for page in page_store.iter_rejected_pages()}


def test_crawl_run_visits_all_reachable_pages(client, tmp_path, page_store, requested_paths):
    run_crawl(client, tmp_path, page_store)

    assert stored_urls(page_store) == [
        "https://host/",
        "https://host/a",
        "https://host/b",
        "https://host/c",
    ]
    # every page is fetched exactly once
    assert sorted(requested_paths) == ["/", "/a", "/b", "/c"]


def test_sitemap_fallback_is_fetched_once(client, tmp_path, page_store, requested_paths):
    pages = {
        "/": page("root"),
        "/sitemap.xml": b"<urlset><url><loc>https://host/fallback</loc></url></urlset>",
        "/fallback": page("fallback"),
    }
    with make_client(pages, requested_paths) as sitemap_client:
        run_crawl(
            sitemap_client,
            tmp_path,
            page_store,
            robots=RobotsCache(sitemap_client),
            sitemap=True,
        )

    assert stored_urls(page_store) == ["https://host/", "https://host/fallback"]
    assert requested_paths.count("/sitemap.xml") == 1


def test_global_lease_is_released_when_fetch_raises(
    monkeypatch, client, tmp_path, page_store, link_store
):
    context = CrawlContext(
        client=client,
        save_dir=tmp_path,
        page_store=page_store,
        link_store=link_store,
        robots=allow_all_robots(),
        user_agent="TestCrawler/1.0",
        page_critic=FakePagePredictor(),
        link_critic=FakeLinkPredictor(),
        state=CrawlState(),
        host_counts={},
        host_reject_counts={},
        max_pages_per_host=None,
    )
    frontier = GlobalFrontier(
        context.state,
        request_delays={0: 0.0},
        max_pages_per_seed={0: None},
        max_discovered_per_seed={0: None},
    )
    frontier.submit(9.0, "https://host/first", 0, 0)
    frontier.submit(8.0, "https://host/second", 0, 0)
    first = frontier.claim()
    assert first is not None

    def fail_fetch(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("tuebingen_crawler.crawler.fetch_page", fail_fetch)
    process_lease(context, make_site(), frontier, first)

    second = frontier.claim()
    assert second is not None and second.entry.url == "https://host/second"


def test_crawl_run_saves_html_files(client, tmp_path, page_store):
    run_crawl(client, tmp_path, page_store)

    for page in page_store.iter_html_pages():
        saved = Path(page.path)
        assert saved.exists()
        assert saved.read_bytes() == PAGES[httpx.URL(page.url).path]


def test_crawl_run_uses_normalized_host_for_storage(tmp_path, page_store):
    with make_client(PAGES, []) as client:
        run_crawl(client, tmp_path, page_store, url="https://www.host/")

    pages = list(page_store.iter_html_pages())
    assert pages
    assert {page.host for page in pages} == {"host"}
    assert all(Path(page.path).parent == tmp_path / "host" for page in pages)


def test_crawl_run_stores_selection_debug_metadata(client, tmp_path, page_store):
    run_crawl(client, tmp_path, page_store)

    pages = {page.url: page for page in page_store.iter_html_pages()}
    root = pages["https://host/"]
    child = pages["https://host/a"]

    assert root.crawl_depth == 0
    assert child.crawl_depth == 1
    assert root.language == "en"
    assert root.relevance is not None and root.relevance > 0.0
    assert root.token_count is not None and root.token_count >= 30


def test_crawl_run_stores_pageverdict_metadata(client, tmp_path, page_store):
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        run_crawl(
            client,
            tmp_path,
            page_store,
            link_store=link_store,
            page_critic=FakePagePredictor(),
        )
        link_row = link_store.con.execute(
            "SELECT parent_pageverdict_score, parent_pageverdict_label, "
            "parent_pageverdict_decision FROM link_candidates "
            "WHERE parent_url = ? AND target_url = ?",
            ("https://host/", "https://host/a"),
        ).fetchone()

    root = {page.url: page for page in page_store.iter_html_pages()}["https://host/"]
    assert root.pageverdict.score == 0.91
    assert root.pageverdict.label == "positive"
    assert root.pageverdict.decision == "index_strong"
    assert root.pageverdict.model == "fake_page_verdict.joblib"
    assert root.pageverdict.snippet is not None
    assert link_row["parent_pageverdict_score"] == 0.91
    assert link_row["parent_pageverdict_label"] == "positive"
    assert link_row["parent_pageverdict_decision"] == "index_strong"


def test_crawl_run_respects_max_pages_per_seed(client, tmp_path, page_store, requested_paths):
    run_crawl(client, tmp_path, page_store, max_pages_per_seed=2)

    assert len(stored_urls(page_store)) == 2
    assert len(requested_paths) == 2


def test_crawl_run_respects_discovered_budget(client, tmp_path, page_store, requested_paths):
    state = run_crawl(client, tmp_path, page_store, max_discovered_per_seed=2)

    assert state.statistics.discovered == 2
    assert len(requested_paths) == 2


def test_crawl_run_skips_fetching_when_host_capped(client, tmp_path, page_store, requested_paths):
    host_counts = {"host": 1}
    state = run_crawl(
        client, tmp_path, page_store, host_counts=host_counts, max_pages_per_host=1
    )

    assert stored_urls(page_store) == []
    assert state.statistics.saved == 0
    assert host_counts["host"] == 1
    assert requested_paths == []


def test_crawl_run_skips_fetching_when_host_reject_budget_exhausted(
    client, tmp_path, page_store, requested_paths
):
    state = run_crawl(
        client,
        tmp_path,
        page_store,
        host_counts={},
        host_reject_counts={"host": HOST_REJECT_CUTOFF},
    )

    assert stored_urls(page_store) == []
    assert state.statistics.saved == 0
    assert requested_paths == []


def test_crawl_run_cap_counts_saved_pages_per_host(client, tmp_path, page_store):
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
        link_critic=FakeLinkPredictor(0.9),
    )

    assert state.frontier == []
    # capped -> not enqueued -> not marked seen, so a stronger parent can retry later
    assert "https://host/a" not in state.seen_urls


def test_evaluate_links_skips_off_topic_exhausted_host(tmp_path):
    state = CrawlState()
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        evaluate_links(
            state=state,
            links=[("https://junk.example/page", "Tübingen")],
            current_url="https://host/",
            depth=0,
            parent_relevance=5.0,
            parent_host="host",
            host_counts={},
            host_reject_counts={"junk.example": HOST_REJECT_CUTOFF},
            max_pages_per_host=None,
            link_critic=FakeLinkPredictor(0.9),
            link_store=link_store,
        )
        [row] = link_store.con.execute(
            "SELECT selected, should_enqueue, rejection_reason FROM link_candidates"
        ).fetchall()

    assert state.frontier == []
    assert "https://junk.example/page" not in state.seen_urls
    assert row["selected"] == 0
    assert row["should_enqueue"] == 0
    assert row["rejection_reason"] == "host_off_topic"


def test_evaluate_links_keeps_host_with_a_save_despite_many_rejects():
    state = CrawlState()
    evaluate_links(
        state=state,
        links=[("https://good.example/page", "Tübingen")],
        current_url="https://host/",
        depth=0,
        parent_relevance=5.0,
        parent_host="host",
        host_counts={"good.example": 1},
        host_reject_counts={"good.example": HOST_REJECT_CUTOFF + 1},
        max_pages_per_host=None,
        link_critic=FakeLinkPredictor(0.9),
    )

    assert len(state.frontier) == 1


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
        link_critic=FakeLinkPredictor(0.9),
    )

    assert len(state.frontier) == 1
    assert "https://host/a" in state.seen_urls


def test_evaluate_links_records_link_candidates(tmp_path):
    state = CrawlState()
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        evaluate_links(
            state=state,
            links=[("/a", "Tübingen")],
            current_url="https://host/",
            depth=0,
            parent_relevance=5.0,
            parent_host="host",
            host_counts={},
            max_pages_per_host=None,
            link_critic=FakeLinkPredictor(0.9),
            link_store=link_store,
        )

        [row] = link_store.con.execute("SELECT * FROM link_candidates").fetchall()

    assert row["parent_url"] == "https://host/"
    assert row["target_url"] == "https://host/a"
    assert row["anchor"] == "Tübingen"
    assert row["should_enqueue"] == 1
    assert row["selected"] == 1
    assert row["parent_relevance"] == 5.0
    assert row["linkverdict_score"] == 0.9
    assert row["linkverdict_label"] == "positive"
    assert row["linkverdict_model"] == "fake_link_verdict.joblib"


def test_evaluate_links_skips_model_verdict_for_skipable_link(tmp_path):
    state = CrawlState()
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        evaluate_links(
            state=state,
            links=[("/image.jpg", "Tübingen photo")],
            current_url="https://host/",
            depth=0,
            parent_relevance=5.0,
            parent_host="host",
            host_counts={},
            max_pages_per_host=None,
            link_critic=FakeLinkPredictor(0.9),
            link_store=link_store,
        )

        [row] = link_store.con.execute("SELECT * FROM link_candidates").fetchall()

    # resource url is hard-skipped before the model, so it carries no verdict
    assert row["should_enqueue"] == 0
    assert row["linkverdict_score"] is None
    assert row["linkverdict_label"] is None
    assert row["linkverdict_model"] is None


def test_evaluate_links_caps_links_per_url_family(tmp_path):
    state = CrawlState()
    # five links all in the same family (host + leading "news" segment)
    links = [(f"/news/{i}", "Tübingen") for i in range(5)]
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        evaluate_links(
            state=state,
            links=links,
            current_url="https://host/",
            depth=0,
            parent_relevance=5.0,
            parent_host="host",
            host_counts={},
            max_pages_per_host=None,
            link_critic=FakeLinkPredictor(0.49),
            link_store=link_store,
        )
        rows = link_store.con.execute(
            "SELECT selected, should_enqueue, rejection_reason FROM link_candidates"
        ).fetchall()

    # only MAX_SELECTED_LINKS_PER_URL_FAMILY of the five are enqueued
    assert len(state.frontier) == 3
    assert sum(row["selected"] for row in rows) == 3
    capped = [row for row in rows if row["rejection_reason"] == "page_family_budget"]
    assert len(capped) == 2
    # capped links would have been enqueued absent the family budget
    assert all(row["should_enqueue"] == 1 for row in capped)


def test_evaluate_links_allows_one_high_confidence_link_beyond_family_cap(tmp_path):
    state = CrawlState()
    links = [(f"/news/{i}", "Tübingen") for i in range(5)]
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        evaluate_links(
            state=state,
            links=links,
            current_url="https://host/",
            depth=0,
            parent_relevance=5.0,
            parent_host="host",
            host_counts={},
            max_pages_per_host=None,
            link_critic=FakeLinkPredictor(0.50),
            link_store=link_store,
        )
        rows = link_store.con.execute(
            "SELECT selected, should_enqueue, rejection_reason FROM link_candidates"
        ).fetchall()

    assert len(state.frontier) == 4
    assert sum(row["selected"] for row in rows) == 4
    capped = [row for row in rows if row["rejection_reason"] == "page_family_budget"]
    assert len(capped) == 1
    assert capped[0]["should_enqueue"] == 1


def test_evaluate_links_caps_links_per_host(tmp_path):
    state = CrawlState()
    # different first path segments avoid the URL-family cap; only the host cap applies
    links = [(f"https://example.com/section-{i}", "Tübingen") for i in range(12)]
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        evaluate_links(
            state=state,
            links=links,
            current_url="https://host/",
            depth=0,
            parent_relevance=5.0,
            parent_host="host",
            host_counts={},
            max_pages_per_host=None,
            link_critic=FakeLinkPredictor(0.9),
            link_store=link_store,
        )
        rows = link_store.con.execute(
            "SELECT selected, should_enqueue, rejection_reason FROM link_candidates"
        ).fetchall()

    assert len(state.frontier) == 8
    assert sum(row["selected"] for row in rows) == 8
    capped = [row for row in rows if row["rejection_reason"] == "page_host_budget"]
    assert len(capped) == 4
    assert all(row["should_enqueue"] == 1 for row in capped)


def test_evaluate_links_passes_saved_host_counts_to_frontier():
    state = CrawlState()
    host_counts = {"host": 3}
    critic = FakeLinkPredictor(0.9)

    evaluate_links(
        state=state,
        links=[("/a", "Tübingen")],
        current_url="https://host/",
        depth=0,
        parent_relevance=5.0,
        parent_host="host",
        host_counts=host_counts,
        max_pages_per_host=5,
        link_critic=critic,
    )

    verdict = classify_link(
        critic,
        anchor="Tübingen",
        target_url="https://host/a",
        target_host="host",
        target_depth=1,
        parent_url="https://host/",
        parent_host="host",
        parent_depth=0,
        parent_relevance=5.0,
        parent_score=None,
        parent_decision="",
    )
    expected_score = (
        LINK_SCORE_WEIGHT * verdict.score
        - 0.7 * 1
        - 0.9 * math.log1p(3)
    )
    assert state.frontier[0].heap_priority == pytest.approx(-expected_score)


def test_crawl_run_updates_statistics(client, tmp_path, page_store):
    state = run_crawl(client, tmp_path, page_store)

    assert state.statistics.fetched == 4
    assert state.statistics.saved == 4
    assert state.statistics.discovered == 4
    assert state.statistics.failed == 0


def test_crawl_run_counts_failed_fetches(tmp_path, page_store, requested_paths):
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

    missing = rejected_records(page_store)["https://host/missing"]
    assert missing.exclusion_reason == "bad_status"
    assert missing.status_code == 404
    assert missing.content_type == "text/html"
    assert missing.crawl_depth == 1
    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        link_row = link_store.con.execute(
            "SELECT target_status, target_status_code, target_exclusion_reason "
            "FROM link_candidates WHERE target_url = ?",
            ("https://host/missing",),
        ).fetchone()
    assert link_row["target_status"] == "rejected"
    assert link_row["target_status_code"] == 404
    assert link_row["target_exclusion_reason"] == "bad_status"


def test_crawl_run_records_non_html_fetch_as_rejected(tmp_path, page_store):
    def handler(request):
        return httpx.Response(
            200, headers={"Content-Type": "application/pdf"}, content=b"%PDF"
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        state = run_crawl(client, tmp_path, page_store)

    assert stored_urls(page_store) == []
    assert state.statistics.failed == 0
    assert state.statistics.saved == 0

    [rejected] = rejected_records(page_store).values()
    assert rejected.url == "https://host/"
    assert rejected.exclusion_reason == "non_html"
    assert rejected.status_code == 200
    assert rejected.content_type == "application/pdf"
    assert rejected.crawl_depth == 0


def test_crawl_run_records_empty_text_as_rejected(tmp_path, page_store):
    pages = {
        "/": b'<html lang="en"><title>T\xc3\xbcbingen</title><body> </body></html>'
    }

    with make_client(pages, []) as client:
        state = run_crawl(client, tmp_path, page_store)

    assert stored_urls(page_store) == []
    assert state.statistics.saved == 0

    [rejected] = rejected_records(page_store).values()
    assert rejected.url == "https://host/"
    assert rejected.title == "Tübingen"
    assert rejected.exclusion_reason == "empty_text"
    assert rejected.status_code == 200
    assert rejected.content_type == "text/html"
    assert rejected.crawl_depth == 0
    assert rejected.token_count == 0


def test_crawl_run_records_duplicate_text_as_rejected(tmp_path, page_store):
    duplicate_body = page('<a href="/copy">Tübingen Copy</a>')
    pages = {
        "/": duplicate_body,
        "/copy": duplicate_body,
    }

    with make_client(pages, []) as client:
        run_crawl(client, tmp_path, page_store)

    assert stored_urls(page_store) == ["https://host/"]

    duplicate = rejected_records(page_store)["https://host/copy"]
    assert duplicate.exclusion_reason == "duplicate_text"
    assert duplicate.status_code == 200
    assert duplicate.content_type == "text/html"
    assert duplicate.language == "en"
    assert duplicate.relevance is not None and duplicate.relevance > 0.0
    assert duplicate.token_count is not None and duplicate.token_count >= 30


def test_crawl_run_skips_request_errors(tmp_path, page_store):
    def handler(request):
        raise httpx.ConnectError("certificate verify failed", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        state = run_crawl(client, tmp_path, page_store)

    assert stored_urls(page_store) == []
    assert state.statistics.failed == 1
    assert state.statistics.saved == 0


def test_crawl_run_rejects_invalid_starting_url(client, tmp_path, page_store):
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


def test_crawl_run_rejects_german_page_but_follows_its_links(
    tmp_path, page_store, requested_paths
):
    # only English content may be indexed; a German page is rejected even with a
    # positive model score, but its links are still followed.
    de_root = (
        '<html lang="de"><title>Tübingen</title>'
        "Die Universitätsstadt Tübingen liegt am Neckar. Tübingen ist alt. "
        "Die Stadt hat eine alte Universität, eine historische Altstadt, "
        "viele Studierende, den Neckar, Museen, Kultur, Forschung und "
        "wichtige Orte für Besucherinnen und Besucher in Baden Württemberg. "
        '<a href="/en">Tübingen in English</a>'
    ).encode("utf-8")
    pages = {"/": de_root, "/en": page("leaf en")}

    with make_client(pages, requested_paths) as client:
        run_crawl(client, tmp_path, page_store)

    assert "https://host/" not in stored_urls(page_store)
    assert "https://host/en" in stored_urls(page_store)
    assert "/en" in requested_paths

    rejected_root = rejected_records(page_store)["https://host/"]
    assert rejected_root.exclusion_reason == "non_english"


# --- crawl_hostname scheduler (weighted round-robin across seeds) -------------


def _alnum(text: str) -> str:
    return "".join(char for char in text.lower() if char.isalnum()) or "root"


def _host_page(host: str, path: str, *links: tuple[str, str]) -> bytes:
    # plenty of page-unique tokens so SimHash never near-dups these similar pages
    unique = " ".join(f"{_alnum(host + path)}u{index}" for index in range(15))
    anchors = "".join(f'<a href="{href}">Tübingen {label}</a>' for href, label in links)
    body = (
        f'<html lang="en"><title>Tübingen {_alnum(host + path)}</title>'
        f"Tübingen page {unique} {unique}. {anchors}"
    )
    return body.encode("utf-8")


def _build_tree(host: str) -> dict[str, bytes]:
    # 9 pages within depth<=2: root -> 4 children -> 1 grandchild each
    return {
        "/": _host_page(host, "/", ("/a", "A"), ("/b", "B"), ("/c", "C"), ("/d", "D")),
        "/a": _host_page(host, "/a", ("/a/x", "AX")),
        "/b": _host_page(host, "/b", ("/b/x", "BX")),
        "/c": _host_page(host, "/c", ("/c/x", "CX")),
        "/d": _host_page(host, "/d", ("/d/x", "DX")),
        "/a/x": _host_page(host, "/a/x"),
        "/b/x": _host_page(host, "/b/x"),
        "/c/x": _host_page(host, "/c/x"),
        "/d/x": _host_page(host, "/d/x"),
    }


def _build_small_tree(host: str) -> dict[str, bytes]:
    return {
        "/": _host_page(host, "/", ("/p", "P"), ("/q", "Q")),
        "/p": _host_page(host, "/p"),
        "/q": _host_page(host, "/q"),
    }


def _run_multihost_crawl(monkeypatch, page_store, tmp_path, host_trees, sites) -> list[str]:
    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, headers=HTML_HEADERS, content=b"")
        body = host_trees.get(request.url.host, {}).get(request.url.path)
        if body is None:
            return httpx.Response(404, headers=HTML_HEADERS)
        return httpx.Response(200, headers=HTML_HEADERS, content=body)

    real_client = httpx.Client
    monkeypatch.setattr(
        scheduler_module.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler)),
    )

    with LinkStore(tmp_path / "pages.sqlite") as link_store:
        crawl_hostname(
            Config(sites=sites, save_dir=tmp_path),
            page_store,
            link_store,
            page_critic=FakePagePredictor(),
            link_critic=FakeLinkPredictor(),
        )

    rows = page_store.con.execute("SELECT host FROM pages ORDER BY id").fetchall()
    return [row["host"] for row in rows]


def test_crawl_hostname_interleaves_seeds(tmp_path, page_store, monkeypatch):
    # seed a has a big frontier, seed b a small one. Sequential crawling would put
    # all of a before any of b; parallel seed workers must let b produce pages first.
    host_trees = {
        "a.example": _build_tree("a.example"),
        "b.example": _build_small_tree("b.example"),
    }
    sites = [make_site(url="https://a.example/"), make_site(url="https://b.example/")]

    hosts_in_order = _run_multihost_crawl(monkeypatch, page_store, tmp_path, host_trees, sites)

    a_positions = [i for i, host in enumerate(hosts_in_order) if host == "a.example"]
    b_positions = [i for i, host in enumerate(hosts_in_order) if host == "b.example"]
    assert a_positions and b_positions
    # b starts producing before a is exhausted -> the seeds are interleaved
    assert min(b_positions) < max(a_positions)


def test_crawl_hostname_crawls_all_seeds_completely(tmp_path, page_store, monkeypatch):
    host_trees = {
        "a.example": _build_tree("a.example"),
        "b.example": _build_tree("b.example"),
    }
    sites = [
        make_site(url="https://a.example/"),
        make_site(url="https://b.example/"),
    ]

    hosts_in_order = _run_multihost_crawl(monkeypatch, page_store, tmp_path, host_trees, sites)

    assert hosts_in_order.count("a.example") == 9
    assert hosts_in_order.count("b.example") == 9
