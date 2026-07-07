from __future__ import annotations

import contextlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx

from .crawler import CrawlRun
from .models import Config
from .save_pages import LinkStore, PageStore
from .storage import RobotsCache
from verdict_ml.link.predict import LinkVerdictPredictor
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)

# pages a worker crawls between stop-flag checks
WORKER_CHUNK = 5


def crawl_hostname(
    config: Config,
    page_store: PageStore,
    link_store: LinkStore,
    page_critic: PageVerdictPredictor,
    link_critic: LinkVerdictPredictor,
) -> None:
    # shared crawl state
    seen_urls: set[str] = set()
    seen_texts: set[int] = set()
    host_counts: dict[str, int] = page_store.host_counts()
    host_reject_counts: dict[str, int] = {}

    # run lifecycle
    with contextlib.ExitStack() as clients:
        runs = _prepare_runs(
            config,
            page_store,
            link_store,
            page_critic,
            link_critic,
            clients,
            seen_urls=seen_urls,
            seen_texts=seen_texts,
            host_counts=host_counts,
            host_reject_counts=host_reject_counts,
        )
        try:
            _run_parallel(runs)
        finally:
            _finalize_runs(runs)


# builds and prepares one CrawlRun per seed
def _prepare_runs(
    config: Config,
    page_store: PageStore,
    link_store: LinkStore,
    page_critic: PageVerdictPredictor,
    link_critic: LinkVerdictPredictor,
    clients: contextlib.ExitStack,
    *,
    seen_urls: set[str],
    seen_texts: set[int],
    host_counts: dict[str, int],
    host_reject_counts: dict[str, int],
) -> list[CrawlRun]:
    headers = {"Accept": config.accept, "User-Agent": config.user_agent}
    # one shared robots.txt cache
    robots = RobotsCache(clients.enter_context(httpx.Client(headers=headers)))
    runs: list[CrawlRun] = []
    for site in config.sites:
        try:
            client = clients.enter_context(
                httpx.Client(timeout=site.request_timeout, headers=headers)
            )
            # skip seeds which categorically disallow crawling
            if not robots.can_fetch(config.user_agent, site.url):
                logger.warning("Skipping %s because robots.txt disallows it", site.url)
                continue

            run = CrawlRun(
                client=client,
                site=site,
                save_dir=config.save_dir,
                save_state_every=config.save_state_every,
                page_store=page_store,
                link_store=link_store,
                robots=robots,
                user_agent=config.user_agent,
                seen_urls=seen_urls,
                seen_texts=seen_texts,
                host_counts=host_counts,
                host_reject_counts=host_reject_counts,
                max_pages_per_host=config.max_pages_per_host,
                page_critic=page_critic,
                link_critic=link_critic,
            )
            run.prepare()
            runs.append(run)
        # one bad seed must not abort the crawl
        except Exception as exc:
            logger.error("Seed %s failed to start; skipping: %s", site.url, exc)
            continue
    return runs


# one thread per seed
def _run_parallel(runs: list[CrawlRun]) -> None:
    if not runs:
        return
    stop = threading.Event()

    def work(run: CrawlRun) -> None:
        try:
            while run.has_work and not stop.is_set():
                run.run_chunk(WORKER_CHUNK)
        except Exception as exc:
            logger.error("Seed %s failed; dropping: %s", run.site.url, exc)

    with ThreadPoolExecutor(max_workers=len(runs)) as pool:
        futures = [pool.submit(work, run) for run in runs]
        try:
            for future in futures:
                future.result()
        except BaseException:
            stop.set()
            raise


def _finalize_runs(runs: list[CrawlRun]) -> None:
    # persist final states
    for run in runs:
        try:
            run.finalize()
        except Exception as exc:
            logger.error("Failed to persist state for %s: %s", run.site.url, exc)
    for run in runs:
        run.state.statistics.print()
