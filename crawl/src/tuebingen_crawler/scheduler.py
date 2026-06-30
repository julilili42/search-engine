from __future__ import annotations

import contextlib
import logging

import httpx

from .crawler import CrawlRun
from .models import Config
from .save_pages import LinkStore, PageStore
from .storage import load_robots
from verdict_ml.link.predict import LinkVerdictPredictor
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)

# pages per scheduler round before next seed
ROUND_ROBIN_CHUNK = 5


def crawl_hostname(
    config: Config,
    page_store: PageStore,
    link_store: LinkStore,
    page_critic: PageVerdictPredictor,
    link_critic: LinkVerdictPredictor,
) -> None:
    # avoids crawling duplicate pages (different urls, same content); shared across seeds
    seen_urls: set[str] = set()
    seen_texts: set[int] = set()
    # saved pages per host shared across seeds and resumed from the db
    host_counts: dict[str, int] = page_store.host_counts()
    # rejected pages per host shared across seeds within this crawl
    host_reject_counts: dict[str, int] = {}

    # Keep every seed's client open for the whole crawl
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
        # finalize() runs in finally so an interrupted crawl still persist
        try:
            _weighted_round_robin(runs)
        finally:
            for run in runs:
                try:
                    run.finalize()
                except Exception as exc:
                    logger.error("Failed to persist state for %s: %s", run.site.url, exc)
            for run in runs:
                run.state.statistics.print()


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
    runs: list[CrawlRun] = []
    for site in config.sites:
        try:
            client = clients.enter_context(
                httpx.Client(timeout=site.request_timeout, headers=headers)
            )
            robot_parser = load_robots(client, site)

            # skips urls which categorically disallow crawling
            if not robot_parser.can_fetch(config.user_agent, site.url):
                logger.warning("Skipping %s because robots.txt disallows it", site.url)
                continue

            run = CrawlRun(
                client=client,
                site=site,
                save_dir=config.save_dir,
                save_state_every=config.save_state_every,
                page_store=page_store,
                link_store=link_store,
                robot_parser=robot_parser,
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
        # one bad seed (network, robots, ...) must not abort the whole crawl
        except Exception as exc:
            logger.error("Seed %s failed to start; skipping: %s", site.url, exc)
            continue
    return runs


# every active seed advances each round with ROUND_ROBIN_CHUNK * round_robin_weight 
def _weighted_round_robin(runs: list[CrawlRun]) -> None:
    active = [run for run in runs if run.has_work]
    while active:
        for run in list(active):
            if not run.has_work:
                active.remove(run)
                continue
            try:
                run.run_chunk(ROUND_ROBIN_CHUNK * run.site.round_robin_weight)
            except Exception as exc:
                logger.error("Seed %s chunk failed; dropping: %s", run.site.url, exc)
                active.remove(run)
