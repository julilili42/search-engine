from __future__ import annotations

import heapq
import math
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from .models import CrawlState, FrontierEntry
from .urls import normalize_host


# link admission
ENQUEUE_FLOOR = 0.05
MAX_DEPTH = 5
LINK_SCORE_WEIGHT = 10.0

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


@dataclass(frozen=True)
class CrawlLease:
    entry: FrontierEntry
    host: str
    claimed_at: float

# One in-process frontier, with one concurrent request per host.
class GlobalFrontier:
    def __init__(
        self,
        state: CrawlState,
        *,
        request_delays: dict[int, float],
        max_pages_per_seed: dict[int, int | None],
        max_discovered_per_seed: dict[int, int | None],
        saved_urls_by_host: dict[str, int] | None = None,
    ) -> None:
        # configuration
        self.state = state
        self.request_delays = request_delays
        self.max_pages_per_seed = max_pages_per_seed
        self.max_discovered_per_seed = max_discovered_per_seed
        self.saved_urls_by_host = saved_urls_by_host if saved_urls_by_host is not None else {}

        # synchronization
        self.lock = threading.RLock()
        self._condition = threading.Condition(self.lock)

        # host scheduling
        self._ready_hosts = []
        self._delayed_hosts = []
        self._queues: dict[str, list[FrontierEntry]] = {}
        self._versions: dict[str, int] = {}
        self._next_allowed: dict[str, float] = {}
        self._host_delays: dict[str, float] = {}
        self._in_flight: set[str] = set()

        # seed scheduling
        self._in_flight_by_seed: dict[int, int] = {}
        self._blocked_hosts_by_seed: dict[int, set[str]] = {}

        queued = list(state.frontier)
        state.frontier.clear()
        state.queued_urls_by_host.clear()
        for entry in queued:
            self._add_entry(entry)
        with self.lock:
            for host in self._queues:
                self._schedule(host)

    # Score a URL using depth and host saturation.
    def _priority_score(self, score: float, depth: int, host: str) -> float:
        queued = self.state.queued_urls_by_host.get(host, 0)
        saved = self.saved_urls_by_host.get(host, 0)
        return score - DEPTH_PENALTY * depth - HOST_SATURATION_PENALTY * math.log1p(queued + saved)

    # Atomically deduplicate and enqueue one URL.
    def submit(
        self, score: float, url: str, depth: int, seed_index: int, *, seed: bool = False
    ) -> bool:
        host = _host(url)
        with self.lock:
            if not seed and url in self.state.seen_urls:
                return False
            self.state.seen_urls.add(url)
            self.state.counter += 1
            priority_score = self._priority_score(score, depth, host)
            self._add_entry(
                FrontierEntry(-priority_score, self.state.counter, url, depth, seed_index), host
            )
            self._schedule(host)
            return True

    # Wait for and lease the globally best eligible URL, or finish when empty.
    def claim(self) -> CrawlLease | None:
        with self.lock:
            while True:
                now = time.monotonic()
                self._promote_ready(now)
                while self._ready_hosts:
                    _, version, host = heapq.heappop(self._ready_hosts)
                    lease = self._claim_host(host, version, now)
                    if lease is not None:
                        return lease

                if self._delayed_hosts:
                    delay = max(0.0, self._delayed_hosts[0][0] - time.monotonic())
                    self._wait(delay)
                elif self._in_flight:
                    self._wait()
                else:
                    return None

    # Claim the best queued URL for one host while the frontier lock is held.
    def _claim_host(self, host: str, version: int, claimed_at: float) -> CrawlLease | None:
        if version != self._versions.get(host) or host in self._in_flight:
            return None
        queue = self._queues.get(host)
        if not queue:
            return None

        entry = heapq.heappop(queue)
        self._decrement_queued(host)
        seed_status = self._seed_status(entry.seed_index)
        if seed_status == "exhausted":
            self._schedule(host)
            return None
        if seed_status == "blocked":
            heapq.heappush(queue, entry)
            self.state.queued_urls_by_host[host] = self.state.queued_urls_by_host.get(host, 0) + 1
            self._blocked_hosts_by_seed.setdefault(entry.seed_index, set()).add(host)
            return None

        self._in_flight.add(host)
        self._in_flight_by_seed[entry.seed_index] = (
            self._in_flight_by_seed.get(entry.seed_index, 0) + 1
        )
        self.state.statistics.discovered += 1
        self.state.seed_statistics.setdefault(
            entry.seed_index, type(self.state.statistics)()
        ).discovered += 1
        return CrawlLease(entry, host, claimed_at)

    # Always release a lease, including after a fetch or parser failure.
    def finish(self, lease: CrawlLease, *, saved: bool) -> None:
        with self.lock:
            self._in_flight.discard(lease.host)
            seed_index = lease.entry.seed_index
            self._in_flight_by_seed[seed_index] = max(
                0, self._in_flight_by_seed.get(seed_index, 1) - 1
            )
            if saved:
                self.state.seed_statistics.setdefault(
                    seed_index, type(self.state.statistics)()
                ).saved += 1
            self._wake_seed_hosts(seed_index)
            self._next_allowed[lease.host] = max(
                self._next_allowed.get(lease.host, 0.0),
                lease.claimed_at + self._host_delays.get(lease.host, 0.0),
            )
            self._schedule(lease.host)
            self._notify()

    def record_fetch(self) -> None:
        with self.lock:
            self.state.statistics.fetched += 1

    # Materialize host queues for the existing JSON state serializer.
    def snapshot(self) -> CrawlState:
        with self.lock:
            self.state.frontier = [entry for queue in self._queues.values() for entry in queue]
            heapq.heapify(self.state.frontier)
            return self.state

    def _add_entry(self, entry: FrontierEntry, host: str | None = None) -> None:
        if host is None:
            host = _host(entry.url)
        queue = self._queues.setdefault(host, [])
        heapq.heappush(queue, entry)
        self.state.queued_urls_by_host[host] = self.state.queued_urls_by_host.get(host, 0) + 1
        self._host_delays[host] = max(
            self._host_delays.get(host, 0.0), self.request_delays.get(entry.seed_index, 0.0)
        )

    def _decrement_queued(self, host: str) -> None:
        count = self.state.queued_urls_by_host.get(host, 0)
        if count <= 1:
            self.state.queued_urls_by_host.pop(host, None)
        else:
            self.state.queued_urls_by_host[host] = count - 1

    def _seed_status(self, seed_index: int) -> str:
        stats = self.state.seed_statistics.setdefault(seed_index, type(self.state.statistics)())
        discovered_limit = self.max_discovered_per_seed.get(seed_index)
        if discovered_limit is not None and stats.discovered >= discovered_limit:
            return "exhausted"
        saved_limit = self.max_pages_per_seed.get(seed_index)
        if saved_limit is None or stats.saved < saved_limit:
            if saved_limit is None or (
                stats.saved + self._in_flight_by_seed.get(seed_index, 0) < saved_limit
            ):
                return "available"
            return "blocked"
        return "exhausted"

    def _wake_seed_hosts(self, seed_index: int) -> None:
        for host in self._blocked_hosts_by_seed.pop(seed_index, set()):
            self._schedule(host)

    def _schedule(self, host: str) -> None:
        if host in self._in_flight or not self._queues.get(host):
            return
        version = self._versions.get(host, 0) + 1
        self._versions[host] = version
        if self._next_allowed.get(host, 0.0) <= time.monotonic():
            heapq.heappush(self._ready_hosts, (self._queues[host][0].heap_priority, version, host))
        else:
            heapq.heappush(self._delayed_hosts, (self._next_allowed[host], version, host))
        self._notify()

    def _promote_ready(self, now: float) -> None:
        while self._delayed_hosts and self._delayed_hosts[0][0] <= now:
            _, version, host = heapq.heappop(self._delayed_hosts)
            if (
                version != self._versions.get(host)
                or host in self._in_flight
                or not self._queues.get(host)
            ):
                continue
            heapq.heappush(self._ready_hosts, (self._queues[host][0].heap_priority, version, host))

    def _wait(self, timeout: float | None = None) -> None:
        self._condition.wait(timeout=timeout)

    def _notify(self) -> None:
        self._condition.notify_all()
