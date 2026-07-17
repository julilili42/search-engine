import math

from tuebingen_crawler.frontier import (
    _push_priority_score,
    count_frontier_hosts,
    host_reject_budget_exhausted,
)
from tuebingen_crawler.models import FrontierEntry


def test_count_frontier_hosts_normalizes_hosts():
    frontier = [
        FrontierEntry(-3.0, 1, "https://www.example.org/a", 1),
        FrontierEntry(-2.0, 2, "https://example.org/b", 1),
        FrontierEntry(-1.0, 3, "https://other.org/", 0),
    ]

    assert count_frontier_hosts(frontier) == {"example.org": 2, "other.org": 1}


def test_host_reject_budget_exhausted_blocks_unproductive_hosts():
    assert host_reject_budget_exhausted({}, {"junk.org": 6}, "junk.org")
    assert not host_reject_budget_exhausted({"uni.example": 50}, {"uni.example": 150}, "uni.example")


def test_push_priority_score_penalizes_depth_and_host_saturation():
    score = _push_priority_score(
        score=10.0,
        depth=2,
        host="example.org",
        queued_urls_by_host={"example.org": 3},
        saved_urls_by_host={"example.org": 6},
    )

    assert score == 10.0 - 0.7 * 2 - 0.9 * math.log1p(9)
