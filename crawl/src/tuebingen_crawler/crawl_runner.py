from __future__ import annotations

import logging
import math
import threading
import time
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .lease_processor import process_claimed_lease
from .frontier import GlobalFrontier
from .models import Config, CrawlContext, CrawlSite, CrawlState
from .paths import crawl_state_path
from .sitemap import ingest_sitemaps
from .stores import LinkStore, PageStore
from .storage import (
    RobotsCache,
    load_crawl_state,
    save_crawl_state,
)
from .verdict_models import VerdictModels
from .urls import validate_start_url

logger = logging.getLogger(__name__)

# Worker-pool entry point for a crawl run.
GLOBAL_FRONTIER_WORKERS = 8


def crawl_hostname(
    config: Config,
    page_store: PageStore,
    link_store: LinkStore,
    verdict_models: VerdictModels,
) -> None:
    state_dir = config.state_dir or config.save_dir
    state_path = crawl_state_path(state_dir)
    state, loaded = load_crawl_state(state_path)
    host_counts = page_store.host_counts()
    state.statistics.saved = max(state.statistics.saved, sum(host_counts.values()))

    with httpx.Client(
        headers={"Accept": config.accept, "Accept-Language": "en", "User-Agent": config.user_agent}
    ) as client:
        robots = RobotsCache(client)
        sites = dict(enumerate(config.sites)) if loaded else _prepare_sites(config, robots)
        frontier = GlobalFrontier(
            state,
            request_delay=config.request_delay,
            max_pages=config.max_pages,
            saved_urls_by_host=host_counts,
        )
        context = CrawlContext(
            config=config,
            client=client,
            state=state,
            page_store=page_store,
            link_store=link_store,
            robots=robots,
            host_counts=host_counts,
            host_reject_counts={},
            verdict_models=verdict_models,
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
                sitemap_urls = robots.site_maps(site.url)
                if sitemap_urls:
                    ingest_sitemaps(
                        context,
                        sitemap_urls,
                        site.url,
                        frontier,
                        seed_index,
                    )
        try:
            _run_global(
                frontier,
                sites,
                context,
                state_path,
            )
        finally:
            save_crawl_state(state_path, frontier.snapshot())
            logger.info(
                "Finished: fetched=%d discovered=%d failed=%d saved=%d",
                state.statistics.fetched,
                state.statistics.discovered,
                state.statistics.failed,
                state.statistics.saved,
            )


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
    state_path: Path,
) -> None:
    if not sites:
        return
    checkpoint_lock = threading.Lock()
    last_checkpoint = time.monotonic()

    def checkpoint() -> None:
        nonlocal last_checkpoint
        if context.config.save_state_every <= 0:
            return
        with checkpoint_lock:
            if time.monotonic() - last_checkpoint < context.config.save_state_every:
                return
            with frontier.lock:
                snapshot = deepcopy(frontier.snapshot())
            last_checkpoint = time.monotonic()
        save_crawl_state(state_path, snapshot)

    def worker() -> None:
        while (lease := frontier.claim()) is not None:
            process_claimed_lease(context, sites.get(lease.entry.seed_index), frontier, lease)
            checkpoint()

    with ThreadPoolExecutor(max_workers=GLOBAL_FRONTIER_WORKERS) as pool:
        for future in [pool.submit(worker) for _ in range(GLOBAL_FRONTIER_WORKERS)]:
            future.result()
