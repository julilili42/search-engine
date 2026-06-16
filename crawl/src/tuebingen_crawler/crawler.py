from __future__ import annotations

import logging
import time
import hashlib
from pathlib import Path
from .models import Statistics, CrawlState, Config, CrawlSite
from .storage import load_state, generate_state_path, load_robots, save_state, maybe_save_state
from .urls import canonical_url, extract_urls, hostname_for_url
from .fetcher import fetch_bytes, save_html
from .save_pages import PageStore
import httpx
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)


def crawl_hostname(config: Config, page_store: PageStore) -> None:
    headers = {"Accept": config.accept, "User-Agent": config.user_agent}

    for site in config.sites:
        with httpx.Client(timeout=site.request_timeout, headers=headers) as client:            
            robot_parser = load_robots(client, site)

            # skips urls which categorically disallow crawling
            if not robot_parser.can_fetch(config.user_agent, site.url):
                logger.warning("Skipping %s because robots.txt disallows it", site.url)
                continue

            state = crawl_site(client, site, config.save_dir, config.save_state_every, page_store, robot_parser, config.user_agent)

            state.statistics.print()

def crawl_site(
    client: httpx.Client,
    site: CrawlSite,
    save_dir: Path, 
    save_state_every: int,
    page_store: PageStore,
    robot_parser: RobotFileParser,
    user_agent: str
) -> CrawlState:
    # restricts crawler to stay on hostname it started on
    allowed_host = hostname_for_url(site.url)
    # normalize starting url
    canonical_start, is_canonical = canonical_url(site.url, site.url, allowed_host)
    if not is_canonical:
        raise ValueError(f"ERROR: starting url {site.url} is not canonical")

    state_path = generate_state_path(save_dir, allowed_host, canonical_start)
    state, loaded = load_state(state_path)

    if loaded:
        if state.head < len(state.queue):
            logger.info("Resuming crawl at %s", state.queue[state.head])
        else:
            logger.info("Crawl state is already complete")
    else:
        state = CrawlState(queue=[canonical_start], head=0, seen={canonical_start: True}, statistics=Statistics())


    while state.head < len(state.queue):
        if site.max_pages >= 0 and state.statistics.saved >= site.max_pages:
            break

        current_url = state.queue[state.head]
        state.head += 1
        state.statistics.inc_discovered()

        if not robot_parser.can_fetch(user_agent, current_url):
            logger.info("Skipping disallowed URL: %s", current_url)
            state.statistics.inc_failed()
            continue

        try:
            fetch_result = fetch_bytes(
                client=client,
                url=current_url,
                retry_delay=site.retry_delay,
                retries=site.retries,
            )
        except Exception as exc:
            logger.error(
                "%-7s | %-3s | %-24s | %s",
                "FAILED",
                "-",
                "-",
                current_url,
            )
            state.statistics.inc_failed()
            continue

        state.statistics.inc_fetched()
        time.sleep(site.request_delay)

        if fetch_result.body is None:
            logger.info(
                "%-7s | %3d | %-24s | %s",
                "SKIPPED",
                fetch_result.status_code,
                fetch_result.content_type,
                current_url,
            )
            continue
        
        logger.info(
            "%-7s | %3d | %-24s | %s",
            "FETCHED",
            fetch_result.status_code,
            fetch_result.content_type,
            current_url,
        )
        try:
            path = save_html(allowed_host, save_dir, current_url, fetch_result.body)
        except Exception as exc:
            logger.error("Failed to save html %s with error %s", current_url, exc)
            state.statistics.inc_failed()
            continue
        
        # add page entry into sqlite db
        page_store.upsert_page(
            url=current_url,
            host=allowed_host,
            path=path,
            status_code=fetch_result.status_code,
            content_type=fetch_result.content_type,
            content_hash=hashlib.sha256(fetch_result.body).hexdigest(),
        )

        state.statistics.inc_saved()

        try:
            extracted_urls = extract_urls(state.seen, fetch_result.body, current_url, allowed_host)
        except Exception as exc:
            logger.error("Failed to extract urls at %s with error %s", current_url, exc)
            state.statistics.inc_failed()
            continue

        state.queue.extend(extracted_urls)
        maybe_save_state(save_state_every, state_path, state)

    save_state(state_path, state)

    return state
