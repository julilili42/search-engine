from __future__ import annotations

import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .lease_processor import CrawlContext, process_claimed_lease
from .frontier import GlobalFrontier
from .models import Config, CrawlSite, CrawlState
from .paths import global_frontier_state_path, global_seen_state_path
from .stores import LinkStore, PageStore
from .storage import (
    RobotsCache,
    load_shared_state,
    load_crawl_state,
    save_shared_state,
    save_crawl_state,
)
from .urls import validate_start_url
from verdict_ml.link.predict import LinkVerdictPredictor
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)

# Worker-pool entry point for a crawl run.
GLOBAL_FRONTIER_WORKERS = 8


def crawl_hostname(
    config: Config,
    page_store: PageStore,
    link_store: LinkStore,
    page_critic: PageVerdictPredictor,
    link_critic: LinkVerdictPredictor,
) -> None:
    state_dir = config.state_dir or config.save_dir
    state_path = global_frontier_state_path(state_dir)
    shared_state_path = global_seen_state_path(state_dir)
    state, loaded = load_crawl_state(state_path)
    state.seen_urls, state.seen_texts = load_shared_state(shared_state_path)
    host_counts = page_store.host_counts()

    with httpx.Client(
        headers={"Accept": config.accept, "User-Agent": config.user_agent}
    ) as client:
        robots = RobotsCache(client)
        sites = _prepare_sites(config, robots)
        frontier = GlobalFrontier(
            state,
            request_delays={seed_index: site.request_delay for seed_index, site in sites.items()},
            max_pages_per_seed={
                seed_index: site.max_pages_per_seed for seed_index, site in sites.items()
            },
            max_discovered_per_seed={
                seed_index: site.max_discovered_per_seed for seed_index, site in sites.items()
            },
            saved_urls_by_host=host_counts,
        )
        if not loaded:
            for seed_index, site in sites.items():
                frontier.submit(
                    math.inf,
                    validate_start_url(site.url),
                    0,
                    seed_index,
                    seed=True,
                )

        context = CrawlContext(
            client=client,
            state=state,
            page_store=page_store,
            link_store=link_store,
            robots=robots,
            user_agent=config.user_agent,
            save_dir=config.save_dir,
            host_counts=host_counts,
            host_reject_counts={},
            max_pages_per_host=config.max_pages_per_host,
            page_critic=page_critic,
            link_critic=link_critic,
        )
        try:
            _run_global(
                frontier,
                sites,
                context,
                config.save_state_every,
                state_path,
                shared_state_path,
            )
        finally:
            save_crawl_state(state_path, frontier.snapshot())
            save_shared_state(shared_state_path, state.seen_urls, state.seen_texts)
            state.statistics.print()


def _prepare_sites(config: Config, robots: RobotsCache) -> dict[int, CrawlSite]:
    eligible_sites = {}
    for seed_index, site in enumerate(config.sites):
        try:
            canonical_url = validate_start_url(site.url)
        except ValueError as exc:
            logger.error("Skipping invalid seed %s: %s", site.url, exc)
            continue

        if not robots.can_fetch(config.user_agent, canonical_url):
            logger.warning("Skipping %s because robots.txt disallows it", site.url)
            continue
        eligible_sites[seed_index] = site
    return eligible_sites


# Run crawl workers and periodically checkpoint state.
def _run_global(
    frontier: GlobalFrontier,
    sites: dict[int, CrawlSite],
    context: CrawlContext,
    save_state_every: int,
    state_path: Path,
    shared_state_path: Path,
) -> None:
    if not sites:
        return
    checkpoint_lock = threading.Lock()
    last_checkpoint = 0

    def checkpoint() -> None:
        nonlocal last_checkpoint
        if save_state_every <= 0:
            return
        with checkpoint_lock, frontier.lock:
            discovered = frontier.state.statistics.discovered
            if discovered - last_checkpoint < save_state_every:
                return
            snapshot = frontier.snapshot()
            last_checkpoint = discovered
            save_crawl_state(state_path, snapshot)
            save_shared_state(shared_state_path, snapshot.seen_urls, snapshot.seen_texts)

    def worker() -> None:
        while (lease := frontier.claim()) is not None:
            process_claimed_lease(context, sites.get(lease.entry.seed_index), frontier, lease)
            checkpoint()

    with ThreadPoolExecutor(max_workers=GLOBAL_FRONTIER_WORKERS) as pool:
        for future in [pool.submit(worker) for _ in range(GLOBAL_FRONTIER_WORKERS)]:
            future.result()
