import math

from tuebingen_crawler.frontier import (
    FrontierQueueConfig,
    _pop_priority_score,
    _push_priority_score,
    _remember_host,
    count_frontier_hosts,
    pop_frontier,
    push_frontier,
)
from tuebingen_crawler.models import CrawlState, FrontierEntry


def test_count_frontier_hosts_normalizes_hosts():
    frontier = [
        FrontierEntry(-3.0, 1, "https://www.example.org/a", 1),
        FrontierEntry(-2.0, 2, "https://example.org/b", 1),
        FrontierEntry(-1.0, 3, "https://other.org/", 0),
    ]

    assert count_frontier_hosts(frontier) == {
        "example.org": 2,
        "other.org": 1,
    }


def test_push_priority_score_penalizes_depth_and_host_saturation():
    score = _push_priority_score(
        score=10.0,
        depth=2,
        host="example.org",
        queued_urls_by_host={"example.org": 3},
        saved_urls_by_host={"example.org": 6},
    )

    assert score == 10.0 - 0.7 * 2 - 0.9 * math.log1p(9)


def test_push_frontier_uses_push_priority_score_for_heap_priority():
    state = CrawlState(queued_urls_by_host={"example.org": 2})

    push_frontier(
        state,
        score=10.0,
        url="https://example.org/a",
        depth=2,
        saved_urls_by_host={"example.org": 3},
    )

    expected_score = 10.0 - 0.7 * 2 - 0.9 * math.log1p(5)
    assert state.frontier == [
        FrontierEntry(-expected_score, 1, "https://example.org/a", 2)
    ]


def test_push_frontier_counts_queued_urls_by_host():
    state = CrawlState()

    push_frontier(state, 10.0, "https://www.example.org/a", 1)
    push_frontier(state, 9.0, "https://example.org/b", 1)

    assert state.queued_urls_by_host == {"example.org": 2}


def test_pop_priority_score_penalizes_recent_pop_hosts():
    entry = FrontierEntry(-10.0, 1, "https://example.org/a", 1)

    assert (
        _pop_priority_score(entry, recent_pop_hosts=["example.org", "example.org"])
        == 8.0
    )


def test_remember_host_tracks_recent_pop_hosts():
    state = CrawlState()

    _remember_host(state, "https://www.example.org/a")

    assert state.recent_pop_hosts == ["example.org"]


def test_remember_host_keeps_recent_window():
    state = CrawlState(recent_pop_hosts=["a.org", "b.org"])
    config = FrontierQueueConfig(recent_host_window=2)

    _remember_host(state, "https://c.org/", config=config)

    assert state.recent_pop_hosts == ["b.org", "c.org"]


def test_pop_frontier_uses_recent_host_penalty_within_window():
    state = CrawlState(
        frontier=[
            FrontierEntry(-10.0, 1, "https://a.org/high", 1),
            FrontierEntry(-9.0, 2, "https://b.org/lower", 1),
        ],
        recent_pop_hosts=["a.org", "a.org"],
        queued_urls_by_host={"a.org": 1, "b.org": 1},
    )
    config = FrontierQueueConfig(pop_window=2)

    assert pop_frontier(state, config=config) == ("https://b.org/lower", 1)
    assert state.frontier == [FrontierEntry(-10.0, 1, "https://a.org/high", 1)]
    assert state.queued_urls_by_host == {"a.org": 1}
    assert state.recent_pop_hosts[-1] == "b.org"
