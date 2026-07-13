from __future__ import annotations

import heapq
import math
from urllib.parse import urlparse

from .models import CrawlState, FrontierEntry
from .urls import normalize_host


# link admission
ENQUEUE_FLOOR = 0.05
MAX_DEPTH = 5
LINK_SCORE_WEIGHT = 10.0

# frontier priority
POP_WINDOW = 128
RECENT_HOST_WINDOW = 8
RECENT_HOST_PENALTY = 1.0
DEPTH_PENALTY = 0.7
HOST_SATURATION_PENALTY = 0.9

# global host budgets
MAX_SAVED_PAGES_PER_HOST = 1000
HOST_REJECT_CUTOFF = 6
HOST_REJECT_RATIO = 10.0


def _host(url: str) -> str:
    try:
        return normalize_host(urlparse(url).hostname)
    except ValueError:
        return ""


def saved_host_at_cap(
    host_counts: dict[str, int], max_pages_per_host: int | None, host: str
) -> bool:
    return max_pages_per_host is not None and host_counts.get(host, 0) >= max_pages_per_host


def host_reject_budget_exhausted(
    host_counts: dict[str, int],
    host_reject_counts: dict[str, int],
    host: str,
) -> bool:
    if HOST_REJECT_CUTOFF <= 0:
        return False
    rejects = host_reject_counts.get(host, 0)
    saves = host_counts.get(host, 0)
    return rejects >= max(HOST_REJECT_CUTOFF, HOST_REJECT_RATIO * saves)


def count_frontier_hosts(frontier: list[FrontierEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in frontier:
        host = _host(entry.url)
        counts[host] = counts.get(host, 0) + 1
    return counts


# priority scoring
def _push_priority_score(
    score: float,
    depth: int,
    host: str,
    *,
    queued_urls_by_host: dict[str, int],
    saved_urls_by_host: dict[str, int],
) -> float:
    queued = queued_urls_by_host.get(host, 0)
    saved = saved_urls_by_host.get(host, 0)
    host_saturation = math.log1p(queued + saved)
    return (
        score
        - DEPTH_PENALTY * depth
        - HOST_SATURATION_PENALTY * host_saturation
    )


def _pop_priority_score(
    entry: FrontierEntry,
    *,
    recent_pop_hosts: list[str] | None = None,
) -> float:
    score = -entry.heap_priority
    recent = recent_pop_hosts or []
    host = _host(entry.url)
    recent_hits = recent.count(host)
    return score - RECENT_HOST_PENALTY * recent_hits


# queue operations
def _remember_host(
    state: CrawlState,
    url: str,
    recent_host_window: int = RECENT_HOST_WINDOW,
) -> None:
    host = _host(url)
    if not host:
        return
    state.recent_pop_hosts.append(host)
    state.recent_pop_hosts = state.recent_pop_hosts[-recent_host_window:]


def push_frontier(
    state: CrawlState,
    score: float,
    url: str,
    depth: int,
    saved_urls_by_host: dict[str, int] | None = None,
) -> None:
    host = _host(url)
    priority_score = _push_priority_score(
        score,
        depth,
        host,
        queued_urls_by_host=state.queued_urls_by_host,
        saved_urls_by_host=saved_urls_by_host or {},
    )
    state.counter += 1
    heapq.heappush(
        state.frontier,
        FrontierEntry(
            heap_priority=-priority_score,
            sequence=state.counter,
            url=url,
            depth=depth,
        ),
    )
    state.queued_urls_by_host[host] = state.queued_urls_by_host.get(host, 0) + 1


def pop_frontier(
    state: CrawlState,
    pop_window: int = POP_WINDOW,
    recent_host_window: int = RECENT_HOST_WINDOW,
) -> tuple[str, int]:
    window_size = min(pop_window, len(state.frontier))
    candidates = [heapq.heappop(state.frontier) for _ in range(window_size)]
    best_index = max(
        range(len(candidates)),
        key=lambda index: _pop_priority_score(
            candidates[index],
            recent_pop_hosts=state.recent_pop_hosts,
        ),
    )
    selected = candidates.pop(best_index)

    for entry in candidates:
        heapq.heappush(state.frontier, entry)

    host = _host(selected.url)
    queued_count = state.queued_urls_by_host.get(host, 0)
    if queued_count <= 1:
        state.queued_urls_by_host.pop(host, None)
    else:
        state.queued_urls_by_host[host] = queued_count - 1
    _remember_host(state, selected.url, recent_host_window=recent_host_window)
    return selected.url, selected.depth
