from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx

from .crawler import CrawlRun
from .models import Config
from .save_pages import LinkStore, PageStore
from .storage import RobotsCache, generate_shared_state_path, load_shared_state, save_shared_state
from verdict_ml.link.predict import LinkVerdictPredictor
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)

# pages a worker crawls between stop-flag checks
WORKER_CHUNK = 5
# fixed worker pool for the global best-first scheduler
# must be smaller then seed count
GLOBAL_FRONTIER_WORKERS = 8


def crawl_hostname(
    config: Config,
    page_store: PageStore,
    link_store: LinkStore,
    page_critic: PageVerdictPredictor,
    link_critic: LinkVerdictPredictor,
) -> None:
    state_dir = config.state_dir or config.save_dir
    shared_state_path = generate_shared_state_path(state_dir)
    seen_urls, seen_texts = load_shared_state(shared_state_path)
    shared_state_lock = threading.Lock()

    def persist_shared_state() -> None:
        with shared_state_lock:
            save_shared_state(shared_state_path, seen_urls, seen_texts)

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
            save_shared_state=persist_shared_state,
            host_counts=host_counts,
            host_reject_counts=host_reject_counts,
        )
        try:
            _run_parallel(runs)
        finally:
            _finalize_runs(runs)
            persist_shared_state()


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
    save_shared_state: Callable[[], None],
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
                state_dir=config.state_dir,
                save_state_every=config.save_state_every,
                page_store=page_store,
                link_store=link_store,
                robots=robots,
                user_agent=config.user_agent,
                seen_urls=seen_urls,
                seen_texts=seen_texts,
                save_shared_state=save_shared_state,
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


# a fixed pool of workers always picks the seed whose best queued link scores highest across all seeds
def _run_parallel(runs: list[CrawlRun]) -> None:
    if not runs:
        return
    stop = threading.Event()
    ready = threading.Condition()
    busy: set[int] = set()
    dead: set[int] = set()

    def _best_available() -> int | None:
        candidates = [
            index
            for index, run in enumerate(runs)
            if index not in busy and index not in dead and run.has_work
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda index: runs[index].head_priority)

    def work() -> None:
        while not stop.is_set():
            with ready:
                index = _best_available()
                while index is None:
                    if not busy:
                        return  
                    ready.wait(timeout=1.0)
                    if stop.is_set():
                        return
                    index = _best_available()
                busy.add(index)
            run = runs[index]
            try:
                run.run_chunk(WORKER_CHUNK)
            except Exception as exc:
                logger.error("Seed %s failed; dropping: %s", run.site.url, exc)
                with ready:
                    dead.add(index)
            finally:
                with ready:
                    busy.discard(index)
                    ready.notify_all()

    worker_count = min(len(runs), GLOBAL_FRONTIER_WORKERS)
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(work) for _ in range(worker_count)]
        try:
            for future in futures:
                future.result()
        except BaseException:
            stop.set()
            with ready:
                ready.notify_all()
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
