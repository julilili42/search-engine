from __future__ import annotations

import heapq
import math
import threading
import time

from .host_scheduler import _HostScheduler
from .models import CrawlLease, CrawlState, FrontierEntry
from .urls import host_from_url


DEPTH_PENALTY = 0.7
HOST_SATURATION_PENALTY = 0.9

# global host budgets
HOST_REJECT_CUTOFF = 6
HOST_REJECT_RATIO = 10.0


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
        host = host_from_url(entry.url)
        counts[host] = counts.get(host, 0) + 1
    return counts


# One request per host: queued -> ready/delayed -> in-flight -> ready/delayed.
class GlobalFrontier:
    def __init__(
        self,
        state: CrawlState,
        *,
        request_delay: float,
        max_pages: int | None,
        saved_urls_by_host: dict[str, int] | None = None,
    ) -> None:
        # configuration
        self.state = state
        self.max_pages = max_pages
        self.saved_urls_by_host = saved_urls_by_host if saved_urls_by_host is not None else {}

        # synchronization
        self.lock = threading.RLock()
        self._condition = threading.Condition(self.lock)

        self._host_scheduler = _HostScheduler(state, request_delay)

        self._in_flight = 0

        queued = state.frontier.copy()
        state.frontier.clear()
        state.queued_urls_by_host.clear()
        for entry in queued:
            self._host_scheduler.enqueue(entry, host_from_url(entry.url))
        with self.lock:
            for host in self._host_scheduler.hosts:
                self._schedule_host(host)

    # Atomically deduplicate and enqueue one URL.
    def submit(
        self, score: float, url: str, depth: int, seed_index: int, *, seed: bool = False
    ) -> bool:
        host = host_from_url(url)
        with self.lock:
            if not seed and url in self.state.seen_urls:
                return False
            self.state.seen_urls.add(url)
            self.state.counter += 1
            priority_score = self._priority_score(score, depth, host)
            self._host_scheduler.enqueue(
                FrontierEntry(-priority_score, self.state.counter, url, depth, seed_index), host
            )
            self._schedule_host(host)
            return True

    # Wait for and lease the globally best eligible URL, or finish when empty.
    def claim(self) -> CrawlLease | None:
        with self.lock:
            while True:
                if self.max_pages is not None:
                    if self.state.statistics.saved >= self.max_pages:
                        return None
                    if self.state.statistics.saved + self._in_flight >= self.max_pages:
                        self._wait()
                        continue
                now = time.monotonic()
                self._host_scheduler.promote_due_hosts(now)
                while ready_host := self._host_scheduler.pop_ready_host():
                    version, host = ready_host
                    lease = self._claim_host(host, version, now)
                    if lease is not None:
                        return lease

                delay = self._host_scheduler.delayed_wait()
                if delay is not None:
                    self._wait(delay)
                elif self._host_scheduler.has_in_flight:
                    self._wait()
                else:
                    return None

    # Always release a lease, including after a fetch or parser failure.
    def finish(self, lease: CrawlLease, *, cooldown_seconds: float = 0.0) -> None:
        with self.lock:
            self._host_scheduler.release(lease.host)
            self._in_flight -= 1
            self._reschedule_host(lease, cooldown_seconds)
            self._notify()

    def record_fetch(self) -> None:
        with self.lock:
            self.state.statistics.fetched += 1

    # Materialize host queues for the existing JSON state serializer.
    def snapshot(self) -> CrawlState:
        with self.lock:
            self.state.frontier = self._host_scheduler.snapshot_entries()
            heapq.heapify(self.state.frontier)
            return self.state

    # Score a URL using depth and host saturation.
    def _priority_score(self, score: float, depth: int, host: str) -> float:
        queued = self.state.queued_urls_by_host.get(host, 0)
        saved = self.saved_urls_by_host.get(host, 0)
        return score - DEPTH_PENALTY * depth - HOST_SATURATION_PENALTY * math.log1p(queued + saved)

    # Claim the best queued URL for one host while the frontier lock is held.
    def _claim_host(self, host: str, version: int, claimed_at: float) -> CrawlLease | None:
        entry = self._host_scheduler.pop_entry(host, version)
        if entry is None:
            return None

        self._host_scheduler.start(host)
        self._in_flight += 1
        self.state.statistics.discovered += 1
        return CrawlLease(entry, host, claimed_at)

    # Host scheduling
    def _reschedule_host(self, lease: CrawlLease, cooldown_seconds: float) -> None:
        self._host_scheduler.set_next_ready_at(lease.host, lease.claimed_at, cooldown_seconds)
        self._schedule_host(lease.host)

    def _schedule_host(self, host: str) -> None:
        self._host_scheduler.schedule(host)
        self._notify()

    def _wait(self, timeout: float | None = None) -> None:
        self._condition.wait(timeout=timeout)

    def _notify(self) -> None:
        self._condition.notify_all()
