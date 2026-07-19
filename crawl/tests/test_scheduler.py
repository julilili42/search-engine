from tuebingen_crawler.frontier import GlobalFrontier
from tuebingen_crawler.models import Config, CrawlState, MAX_SAVED_PAGES_PER_HOST


def make_frontier(**limits):
    return GlobalFrontier(
        CrawlState(),
        request_delays=limits.pop("request_delays", {0: 0.0, 1: 0.0}),
        max_pages_per_seed=limits.pop("max_pages_per_seed", {0: None, 1: None}),
        max_discovered_per_seed=limits.pop(
            "max_discovered_per_seed", {0: None, 1: None}
        ),
    )


def test_config_limits_pages_per_host_by_default():
    assert Config().max_pages_per_host == MAX_SAVED_PAGES_PER_HOST


def test_global_frontier_picks_the_best_url_not_the_best_seed_head():
    frontier = make_frontier()
    frontier.submit(1.0, "https://a.test/low", 0, 0)
    frontier.submit(9.0, "https://b.test/high", 0, 1)
    frontier.submit(8.0, "https://b.test/next", 0, 1)

    first = frontier.claim()
    assert first is not None and first.entry.url == "https://b.test/high"
    frontier.finish(first, saved=False)
    second = frontier.claim()
    assert second is not None and second.entry.url == "https://b.test/next"


def test_global_frontier_releases_a_host_after_a_failed_lease():
    frontier = make_frontier()
    frontier.submit(9.0, "https://host.test/first", 0, 0)
    frontier.submit(8.0, "https://host.test/second", 0, 0)

    first = frontier.claim()
    assert first is not None
    frontier.finish(first, saved=False)
    second = frontier.claim()

    assert second is not None and second.entry.url == "https://host.test/second"


def test_global_frontier_delays_a_cooled_down_host():
    frontier = make_frontier()
    frontier.submit(9.0, "https://host.test/first", 0, 0)
    lease = frontier.claim()
    assert lease is not None

    before = time.monotonic()
    frontier.finish(lease, saved=False, cooldown_seconds=60.0)

    assert frontier._host_scheduler._states[lease.host].next_ready_at >= before + 60.0


def test_global_frontier_updates_a_host_head_lazily():
    frontier = make_frontier()
    frontier.submit(1.0, "https://a.test/low", 0, 0)
    frontier.submit(10.0, "https://a.test/high", 0, 0)
    frontier.submit(5.0, "https://b.test/middle", 0, 1)

    lease = frontier.claim()

    assert lease is not None and lease.entry.url == "https://a.test/high"


def test_global_frontier_keeps_a_seed_page_cap_with_multiple_hosts():
    frontier = make_frontier(max_pages_per_seed={0: 1, 1: None})
    frontier.submit(9.0, "https://a.test/first", 0, 0)
    frontier.submit(8.0, "https://b.test/second", 0, 0)

    first = frontier.claim()
    assert first is not None
    frontier.finish(first, saved=True)

    assert frontier.claim() is None
import time
