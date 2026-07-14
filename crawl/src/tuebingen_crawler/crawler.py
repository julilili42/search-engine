from __future__ import annotations

import logging
import math
from collections.abc import Callable

import httpx
from urllib.parse import urlparse
from pathlib import Path

from .models import CrawlState, CrawlSite
from .storage import (
    RobotsCache,
    generate_state_path,
    load_or_create_state,
    save_state,
    maybe_save_state,
)
from .urls import validate_start_url, normalize_host
from .fetcher import fetch_page
from .frontier import saved_host_at_cap, host_reject_budget_exhausted, pop_frontier
from .page_evaluation import evaluate_page
from .link_evaluation import evaluate_links
from .save_pages import LinkStore, PageStore
from verdict_ml.link.predict import LinkVerdictPredictor
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)


class CrawlRun:
    def __init__(
        self,
        *,
        client: httpx.Client,
        site: CrawlSite,
        save_dir: Path,
        save_state_every: int,
        page_store: PageStore,
        robots: RobotsCache,
        user_agent: str,
        link_store: LinkStore,
        seen_urls: set[str] | None = None,
        seen_texts: set[int] | None = None,
        host_counts: dict[str, int] | None = None,
        host_reject_counts: dict[str, int] | None = None,
        max_pages_per_host: int | None = None,
        page_critic: PageVerdictPredictor,
        link_critic: LinkVerdictPredictor,
        state_dir: Path | None = None,
        save_shared_state: Callable[[], None] | None = None,
    ) -> None:
        self.client = client
        self.site = site
        self.save_dir = save_dir
        self.state_dir = state_dir or save_dir
        self.save_shared_state = save_shared_state
        self.save_state_every = save_state_every
        self.page_store = page_store
        self.link_store = link_store
        self.robots = robots
        self.user_agent = user_agent
        self.seen_urls = seen_urls if seen_urls is not None else set()
        self.seen_texts = seen_texts if seen_texts is not None else set()
        self.host_counts = host_counts if host_counts is not None else {}
        self.host_reject_counts = host_reject_counts if host_reject_counts is not None else {}
        self.max_pages_per_host = max_pages_per_host
        self.page_critic = page_critic
        self.link_critic = link_critic
        self._state: CrawlState | None = None
        self._state_path: Path | None = None

    @property
    def state(self) -> CrawlState:
        if self._state is None:
            raise RuntimeError("CrawlRun state is not initialized")
        return self._state

    @property
    def state_path(self) -> Path:
        if self._state_path is None:
            raise RuntimeError("CrawlRun state path is not initialized")
        return self._state_path

    @property
    def _saturated(self) -> bool:
        return any(
            limit is not None and value >= limit
            for value, limit in (
                (self.state.statistics.saved, self.site.max_pages_per_seed),
                (self.state.statistics.discovered, self.site.max_discovered_per_seed),
            )
        )

    @property
    def has_work(self) -> bool:
        return bool(self._state and self._state.frontier) and not self._saturated

    @property
    def head_priority(self) -> float:
        if not (self._state and self._state.frontier):
            return math.inf
        return self._state.frontier[0].heap_priority

    def prepare(self) -> None:
        canonical_start = validate_start_url(self.site.url)
        hostname = normalize_host(urlparse(canonical_start).hostname)

        self._state_path = generate_state_path(self.state_dir, hostname, canonical_start)
        self._state = load_or_create_state(
            self._state_path, canonical_start, self.seen_urls, self.seen_texts
        )

    def run_chunk(self, max_pages: int | None = None) -> None:
        processed = 0
        while self.has_work and (max_pages is None or processed < max_pages):
            self._process_next()
            processed += 1

    def _process_next(self) -> None:
        current_url, depth = pop_frontier(self.state)
        self.state.statistics.discovered += 1

        hostname = normalize_host(urlparse(current_url).hostname)
        if saved_host_at_cap(self.host_counts, self.max_pages_per_host, hostname):
            return
        if host_reject_budget_exhausted(self.host_counts, self.host_reject_counts, hostname):
            return

        if not self.robots.can_fetch(self.user_agent, current_url):
            logger.debug("Skipping disallowed URL: %s", current_url)
            self.state.statistics.failed += 1
            return

        fetch_result = fetch_page(self.client, current_url, self.site, self.state)
        if fetch_result is None:
            return

        follow_links = evaluate_page(
            page_store=self.page_store,
            link_store=self.link_store,
            save_dir=self.save_dir,
            seen_texts=self.seen_texts,
            host_counts=self.host_counts,
            host_reject_counts=self.host_reject_counts,
            state=self.state,
            page_critic=self.page_critic,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
        )
        if follow_links is None:
            return
        links, relevance, pageverdict = follow_links

        # link extraction runs for every relevant page
        evaluate_links(
            state=self.state,
            links=links,
            current_url=current_url,
            depth=depth,
            parent_relevance=relevance,
            parent_host=hostname,
            host_counts=self.host_counts,
            host_reject_counts=self.host_reject_counts,
            max_pages_per_host=self.max_pages_per_host,
            link_critic=self.link_critic,
            link_store=self.link_store,
            parent_pageverdict=pageverdict,
        )

        if maybe_save_state(self.save_state_every, self.state_path, self.state) and self.save_shared_state:
            self.save_shared_state()

    def finalize(self) -> None:
        save_state(self.state_path, self.state)
        if self.save_shared_state:
            self.save_shared_state()

    def run(self) -> CrawlState:
        self.prepare()
        self.run_chunk()
        self.finalize()
        return self.state
