from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field

from .models import CrawlState, FrontierEntry


@dataclass
class HostState:
    queue: list[FrontierEntry] = field(default_factory=list)
    version: int = 0
    next_ready_at: float = 0.0
    in_flight: bool = False


# Schedules ready/delayed hosts; each HostState owns its URL heap.
class _HostScheduler:
    def __init__(self, state: CrawlState, request_delay: float) -> None:
        self.state = state
        self.request_delay = request_delay
        self._ready_hosts = []
        self._delayed_hosts = []
        self._states: dict[str, HostState] = {}

    def enqueue(self, entry: FrontierEntry, host: str) -> None:
        state = self._states.setdefault(host, HostState())
        heapq.heappush(state.queue, entry)
        self.state.queued_urls_by_host[host] = self.state.queued_urls_by_host.get(host, 0) + 1

    def schedule(self, host: str) -> None:
        state = self._states.get(host)
        if state is None or state.in_flight or not state.queue:
            return
        state.version += 1  # Invalidates stale heap entries.
        if state.next_ready_at <= time.monotonic():
            heapq.heappush(self._ready_hosts, (state.queue[0].heap_priority, state.version, host))
        else:
            heapq.heappush(self._delayed_hosts, (state.next_ready_at, state.version, host))

    def promote_due_hosts(self, now: float) -> None:
        while self._delayed_hosts and self._delayed_hosts[0][0] <= now:
            _, version, host = heapq.heappop(self._delayed_hosts)
            state = self._states.get(host)
            if state is None or version != state.version or state.in_flight or not state.queue:
                continue
            heapq.heappush(self._ready_hosts, (state.queue[0].heap_priority, version, host))

    def pop_ready_host(self) -> tuple[int, str] | None:
        if not self._ready_hosts:
            return None
        _, version, host = heapq.heappop(self._ready_hosts)
        return version, host

    def pop_entry(self, host: str, version: int) -> FrontierEntry | None:
        state = self._states.get(host)
        if state is None or version != state.version or state.in_flight or not state.queue:
            return None
        entry = heapq.heappop(state.queue)
        self._decrement_queued(host)
        return entry

    def requeue(self, host: str, entry: FrontierEntry) -> None:
        heapq.heappush(self._states[host].queue, entry)
        self.state.queued_urls_by_host[host] = self.state.queued_urls_by_host.get(host, 0) + 1

    def start(self, host: str) -> None:
        self._states[host].in_flight = True

    def release(self, host: str) -> None:
        self._states[host].in_flight = False

    def set_next_ready_at(self, host: str, claimed_at: float, cooldown_seconds: float) -> None:
        state = self._states[host]
        state.next_ready_at = max(
            state.next_ready_at,
            claimed_at + self.request_delay,
            time.monotonic() + cooldown_seconds,
        )

    def delayed_wait(self) -> float | None:
        if not self._delayed_hosts:
            return None
        return max(0.0, self._delayed_hosts[0][0] - time.monotonic())

    def snapshot_entries(self) -> list[FrontierEntry]:
        return [entry for state in self._states.values() for entry in state.queue]

    @property
    def hosts(self) -> list[str]:
        return list(self._states)

    @property
    def has_in_flight(self) -> bool:
        return any(state.in_flight for state in self._states.values())

    def _decrement_queued(self, host: str) -> None:
        count = self.state.queued_urls_by_host.get(host, 0)
        if count <= 1:
            self.state.queued_urls_by_host.pop(host, None)
        else:
            self.state.queued_urls_by_host[host] = count - 1
