from __future__ import annotations

import logging
from pathlib import Path
from .models import CrawlState, Config, CrawlSite
from .storage import load_state, generate_state_path, load_robots, save_state, maybe_save_state, save_html
from .urls import validate_start_url, canonical_url, normalize_host
from .fetcher import fetch_page
from .extract import parse_page
from .heuristic import evaluate_page, link_score, should_enqueue
from .save_pages import PageStore
from .frontier import push_frontier, pop_frontier
from .dedup import simhash, is_near_duplicate
import httpx
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse


logger = logging.getLogger(__name__)

# seed links have highest possible priority
SEED_SCORE = 1_000_000.0

# crawls hostnames defined in seed.toml
def crawl_hostname(config: Config, page_store: PageStore) -> None:
    headers = {"Accept": config.accept, "User-Agent": config.user_agent}
    # avoids crawling duplicate pages
    # page might have different urls but same content
    seen_urls: set[str] = set()
    seen_texts: set[int] = set()

    for site in config.sites:
        with httpx.Client(timeout=site.request_timeout, headers=headers) as client:
            robot_parser = load_robots(client, site)

            # skips urls which categorically disallow crawling
            if not robot_parser.can_fetch(config.user_agent, site.url):
                logger.warning("Skipping %s because robots.txt disallows it", site.url)
                continue

            state = crawl_site(
                client,
                site,
                config.save_dir,
                config.save_state_every,
                page_store,
                robot_parser,
                config.user_agent,
                seen_urls,
                seen_texts
            )

            state.statistics.print()

# crawls individual side
def crawl_site(
    client: httpx.Client,
    site: CrawlSite,
    save_dir: Path,
    save_state_every: int,
    page_store: PageStore,
    robot_parser: RobotFileParser,
    user_agent: str,
    seen_urls: set[str] | None = None,
    seen_texts: set[int] | None = None
) -> CrawlState:
    seen_urls = seen_urls if seen_urls is not None else set()
    seen_texts = seen_texts if seen_texts is not None else set()

    canonical_start = validate_start_url(site.url)
    hostname = normalize_host(urlparse(canonical_start).hostname)

    state_path = generate_state_path(save_dir, hostname, canonical_start)
    state = load_or_create_state(state_path, canonical_start, seen_urls, seen_texts)

    # crawling continues until the heap is empty or (optional) max_page is reached.
    while state.frontier:
        if site.max_pages is not None and site.max_pages >= 0 and state.statistics.saved >= site.max_pages:
            break

        current_url, depth = pop_frontier(state)
        state.statistics.discovered += 1

        if not robot_parser.can_fetch(user_agent, current_url):
            logger.info("Skipping disallowed URL: %s", current_url)
            state.statistics.failed += 1
            continue

        fetch_result = fetch_page(client, current_url, site, state)

        if fetch_result is None:
            continue

        if fetch_result.body is None:
            status = fetch_result.status_code
            bad_status = status < 200 or status >= 300
            if bad_status:
                state.statistics.failed += 1
            logger.info(
                "%-7s | %3d | %-24s | %s",
                "FAILED" if bad_status else "SKIPPED",
                status,
                fetch_result.content_type,
                current_url,
            )
            continue

        try:
            page = parse_page(fetch_result.body)
        except Exception as exc:
            logger.error("Failed to parse %s with error %s", current_url, exc)
            state.statistics.failed += 1
            continue
        
        if not page.text.strip():
            continue

        # calculate PageVerdict to rank importance of url in relationship to topic
        verdict = evaluate_page(current_url, page.title, page.text, page.lang)

        if not verdict.is_relevant:
            logger.info(
                "%-7s | %3d | rel=%5.1f | %s",
                "OFFTOPIC",
                fetch_result.status_code,
                verdict.relevance,
                current_url,
            )
            continue

        if verdict.keep:
            # avoids recrawling the same content
            fingerprint = simhash(page.text)
            if page.text and is_near_duplicate(fingerprint, seen_texts):
                logger.info("Skipping duplicate text: %s", current_url)
                continue
            seen_texts.add(fingerprint)
            
            try:
                hostname = normalize_host(urlparse(current_url).hostname)
                path = save_html(hostname, save_dir, current_url, fetch_result.body)
            except Exception as exc:
                logger.error("Failed to save html %s with error %s", current_url, exc)
                state.statistics.failed += 1
                continue

            # write crawl information into sqlite db
            page_store.upsert_page(
                title=page.title,
                url=current_url,
                host=hostname,
                path=path,
                status_code=fetch_result.status_code,
                content_type=fetch_result.content_type,
            )
            state.statistics.saved += 1

            # page is kept therefore eval. of all links on current url
            # add relevant urls to the frontier
            evaluate_links(
                state=state,
                links=page.links,
                current_url=current_url,
                depth=depth,
                parent_relevance=verdict.relevance,
                parent_host=hostname,
            )

            logger.info(
                "%-7s | %3d | rel=%5.1f | %s",
                "SAVED",
                fetch_result.status_code,
                verdict.relevance,
                current_url,
            )
        else:
            logger.info(
                "%-7s | %3d | lang=%s | %s",
                "NON-EN",
                fetch_result.status_code,
                verdict.language,
                current_url,
            )

        maybe_save_state(save_state_every, state_path, state)

    save_state(state_path, state)

    return state


# add relevant urls on current_url to frontier
def evaluate_links(
    state: CrawlState,
    links: list[tuple[str, str]],
    current_url: str,
    depth: int,
    parent_relevance: float,
    parent_host: str,
) -> None:
    child_depth = depth + 1

    for href, anchor in links:
        final_url, is_canonical = canonical_url(href, current_url)
        if not is_canonical or final_url in state.seen_urls:
            continue

        score = link_score(anchor, final_url, parent_relevance, parent_host)
        if should_enqueue(score, child_depth):
            push_frontier(state, score, final_url, child_depth)

        state.seen_urls.add(final_url)


# load intermediate state or start a new one
def load_or_create_state(
    state_path: Path,
    canonical_start: str,
    seen_urls: set[str],
    seen_texts: set[int],
) -> CrawlState:
    state, loaded = load_state(state_path)

    seen_urls.update(state.seen_urls)
    seen_texts.update(state.seen_texts)
    state.seen_urls = seen_urls
    state.seen_texts = seen_texts

    if loaded:
        if state.frontier:
            logger.info("Resuming crawl with %d queued links", len(state.frontier))
        else:
            logger.info("Crawl state is already complete")
        return state

    state.seen_urls.add(canonical_start)
    push_frontier(state, SEED_SCORE, canonical_start, depth=0)
    return state
