import math
from pathlib import Path
from urllib.robotparser import RobotFileParser

import httpx
import pytest

from tuebingen_crawler.crawler import CrawlRun, evaluate_links
from tuebingen_crawler.link_classifier import classify_link
from tuebingen_crawler.models import CrawlSite, CrawlState
from tuebingen_crawler.save_pages import LinkStore, PageStore
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
            prob = 0.9 if ("tübingen" in text or "tuebingen" in text) else 0.1
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


def run_crawl(
    client,
    tmp_path,
    page_store,
    link_store=None,
    seen_urls=None,
    host_counts=None,
    max_pages_per_host=None,
    page_critic=None,
    link_critic=None,
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
                max_pages_per_host=max_pages_per_host,
                page_critic=page_critic,
                link_critic=link_critic,
                **site_overrides,
            )

    return CrawlRun(
        client=client,
        site=make_site(**site_overrides),
        save_dir=tmp_path,
        save_state_every=10,
        page_store=page_store,
        link_store=link_store,
        robot_parser=allow_all_robots(),
        user_agent="TestCrawler/1.0",
        seen_urls=seen_urls,
        host_counts=host_counts,
        max_pages_per_host=max_pages_per_host,
        page_critic=page_critic,
        link_critic=link_critic,
    ).run()


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


def test_crawl_run_skips_fetching_when_host_capped(client, tmp_path, page_store, requested_paths):
    host_counts = {"host": 1}
    state = run_crawl(
        client, tmp_path, page_store, host_counts=host_counts, max_pages_per_host=1
    )

    assert stored_urls(page_store) == []
    assert state.statistics.saved == 0
    assert host_counts["host"] == 1
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
    expected_score = verdict.frontier_score - 0.7 * 1 - 0.9 * math.log1p(3)
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


def test_crawl_run_resumes_completed_state_without_fetching(client, tmp_path, page_store, requested_paths):
    first = run_crawl(client, tmp_path, page_store)
    fetches_first_run = len(requested_paths)

    second = run_crawl(client, tmp_path, page_store)

    assert second.frontier == first.frontier
    # state was complete, so the second run performs no requests
    assert len(requested_paths) == fetches_first_run


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
