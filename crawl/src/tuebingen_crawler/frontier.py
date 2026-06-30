from __future__ import annotations

import heapq
import math
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from .models import CrawlState, FrontierEntry
from .urls import normalize_host


@dataclass(frozen=True)
class FrontierQueueConfig:
    pop_window: int = 128
    recent_host_window: int = 8
    recent_host_penalty: float = 1.0
    depth_penalty: float = 0.7
    host_saturation_penalty: float = 0.9


FRONTIER_QUEUE_CONFIG = FrontierQueueConfig()
REJECT_CUTOFF = int(os.environ.get("CRAWL_HOST_REJECT_CUTOFF", "6"))


def _host(url: str) -> str:
    try:
        return normalize_host(urlparse(url).hostname)
    except ValueError:
        return ""


# caps the number of saved pages per hostname: forces the crawler to spread out
def _host_at_cap(host_counts: dict[str, int], max_pages_per_host: int | None, host: str) -> bool:
    return max_pages_per_host is not None and host_counts.get(host, 0) >= max_pages_per_host


def _host_off_topic_exhausted(
    host_counts: dict[str, int], host_reject_counts: dict[str, int], host: str
) -> bool:
    if REJECT_CUTOFF <= 0:
        return False
    return host_reject_counts.get(host, 0) >= REJECT_CUTOFF and host_counts.get(host, 0) == 0


def count_frontier_hosts(frontier: list[FrontierEntry]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in frontier:
        host = _host(entry.url)
        counts[host] = counts.get(host, 0) + 1
    return counts


def _push_priority_score(
    score: float,
    depth: int,
    host: str,
    *,
    queued_urls_by_host: dict[str, int],
    saved_urls_by_host: dict[str, int],
    config: FrontierQueueConfig = FRONTIER_QUEUE_CONFIG,
) -> float:
    queued = queued_urls_by_host.get(host, 0)
    saved = saved_urls_by_host.get(host, 0)
    host_saturation = math.log1p(queued + saved)
    return (
        score
        - config.depth_penalty * depth
        - config.host_saturation_penalty * host_saturation
    )


def _pop_priority_score(
    entry: FrontierEntry,
    *,
    recent_pop_hosts: list[str] | None = None,
    config: FrontierQueueConfig = FRONTIER_QUEUE_CONFIG,
) -> float:
    score = -entry.heap_priority
    recent = recent_pop_hosts or []
    host = _host(entry.url)
    recent_hits = recent.count(host)
    return score - config.recent_host_penalty * recent_hits


def _remember_host(
    state: CrawlState,
    url: str,
    config: FrontierQueueConfig = FRONTIER_QUEUE_CONFIG,
) -> None:
    host = _host(url)
    if not host:
        return
    state.recent_pop_hosts.append(host)
    state.recent_pop_hosts = state.recent_pop_hosts[-config.recent_host_window :]


# pushes on the min-heap
def push_frontier(
    state: CrawlState,
    score: float,
    url: str,
    depth: int,
    saved_urls_by_host: dict[str, int] | None = None,
    config: FrontierQueueConfig = FRONTIER_QUEUE_CONFIG,
) -> None:
    host = _host(url)
    priority_score = _push_priority_score(
        score,
        depth,
        host,
        queued_urls_by_host=state.queued_urls_by_host,
        saved_urls_by_host=saved_urls_by_host or {},
        config=config,
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


# pops from a small best-first window, then applies recent-host diversity
def pop_frontier(
    state: CrawlState,
    config: FrontierQueueConfig = FRONTIER_QUEUE_CONFIG,
) -> tuple[str, int]:
    window_size = min(config.pop_window, len(state.frontier))
    candidates = [heapq.heappop(state.frontier) for _ in range(window_size)]
    best_index = max(
        range(len(candidates)),
        key=lambda index: _pop_priority_score(
            candidates[index],
            recent_pop_hosts=state.recent_pop_hosts,
            config=config,
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
    _remember_host(state, selected.url, config=config)
    return selected.url, selected.depth
