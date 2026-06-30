from __future__ import annotations

import logging
import httpx
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse
from pathlib import Path
from .models import CrawlState, Config, CrawlSite, FetchResult
from .storage import (
    generate_state_path,
    load_or_create_state,
    load_robots,
    save_state,
    maybe_save_state,
    save_html,
)
from .urls import validate_start_url, canonical_url, normalize_host
from .fetcher import fetch_page
from .extract import parse_page
from .page_classifier import PageIndexExclusion, PageVerdict, classify_page
from .link_classifier import classify_link
from .save_pages import LinkCandidateRecord, LinkStore, PageStore, PageVerdictMetadata
from .frontier import push_frontier, pop_frontier
from .dedup import simhash, is_near_duplicate
from verdict_ml.link.predict import LinkVerdictPredictor
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)

# crawls hostnames defined in seed.toml
def crawl_hostname(
    config: Config,
    page_store: PageStore,
    link_store: LinkStore,
    page_critic: PageVerdictPredictor,
    link_critic: LinkVerdictPredictor | None = None,
) -> None:
    headers = {"Accept": config.accept, "User-Agent": config.user_agent}
    # avoids crawling duplicate pages
    # page might have different urls but same content
    seen_urls: set[str] = set()
    seen_texts: set[int] = set()
    # saved pages per host shared across seeds and resumed from the db
    host_counts: dict[str, int] = page_store.host_counts()

    for site in config.sites:
        with httpx.Client(timeout=site.request_timeout, headers=headers) as client:
            robot_parser = load_robots(client, site)

            # skips urls which categorically disallow crawling
            if not robot_parser.can_fetch(config.user_agent, site.url):
                logger.warning("Skipping %s because robots.txt disallows it", site.url)
                continue

            state = CrawlRun(
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
                max_pages_per_host=config.max_pages_per_host,
                page_critic=page_critic,
                link_critic=link_critic,
            ).run()

            state.statistics.print()

class CrawlRun:
    def __init__(
        self,
        *,
        client: httpx.Client,
        site: CrawlSite,
        save_dir: Path,
        save_state_every: int,
        page_store: PageStore,
        robot_parser: RobotFileParser,
        user_agent: str,
        link_store: LinkStore,
        seen_urls: set[str] | None = None,
        seen_texts: set[int] | None = None,
        host_counts: dict[str, int] | None = None,
        max_pages_per_host: int | None = None,
        page_critic: PageVerdictPredictor,
        link_critic: LinkVerdictPredictor | None = None,
    ) -> None:
        self.client = client
        self.site = site
        self.save_dir = save_dir
        self.save_state_every = save_state_every
        self.page_store = page_store
        self.link_store = link_store
        self.robot_parser = robot_parser
        self.user_agent = user_agent
        self.seen_urls = seen_urls if seen_urls is not None else set()
        self.seen_texts = seen_texts if seen_texts is not None else set()
        self.host_counts = host_counts if host_counts is not None else {}
        self.max_pages_per_host = max_pages_per_host
        self.page_critic = page_critic
        self.link_critic = link_critic
        self._state: CrawlState | None = None

    @property
    def state(self) -> CrawlState:
        if self._state is None:
            raise RuntimeError("CrawlRun state is not initialized")
        return self._state

    # crawls individual side
    def run(self) -> CrawlState:
        canonical_start = validate_start_url(self.site.url)
        hostname = normalize_host(urlparse(canonical_start).hostname)

        state_path = generate_state_path(self.save_dir, hostname, canonical_start)
        state = load_or_create_state(
            state_path, canonical_start, self.seen_urls, self.seen_texts
        )
        self._state = state

        # crawling continues until the heap is empty or (optional) max_page is reached.
        while self.state.frontier:
            if (
                self.site.max_pages_per_seed is not None
                and self.site.max_pages_per_seed >= 0
                and self.state.statistics.saved >= self.site.max_pages_per_seed
            ):
                break

            current_url, depth = pop_frontier(self.state)
            self.state.statistics.discovered += 1

            hostname = normalize_host(urlparse(current_url).hostname)
            if _host_at_cap(self.host_counts, self.max_pages_per_host, hostname):
                continue

            if not self.robot_parser.can_fetch(self.user_agent, current_url):
                logger.debug("Skipping disallowed URL: %s", current_url)
                self.state.statistics.failed += 1
                continue

            fetch_result = fetch_page(self.client, current_url, self.site, self.state)

            if fetch_result is None:
                continue

            follow_links = self.process_fetched_page(
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
            )
            if follow_links is None:
                continue
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
                max_pages_per_host=self.max_pages_per_host,
                link_critic=self.link_critic,
                link_store=self.link_store,
                parent_pageverdict=pageverdict,
            )

            maybe_save_state(self.save_state_every, state_path, self.state)

        save_state(state_path, self.state)

        return self.state

    def process_fetched_page(
        self,
        *,
        current_url: str,
        hostname: str,
        depth: int,
        fetch_result: FetchResult,
    ) -> tuple[list[tuple[str, str]], float, PageVerdictMetadata] | None:
        if fetch_result.body is None:
            status = fetch_result.status_code
            bad_status = status < 200 or status >= 300
            self.reject_page(
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
                exclusion_reason="bad_status" if bad_status else "non_html",
            )
            if bad_status:
                self.state.statistics.failed += 1
            logger.debug(
                "%-7s | %3d | %-10s | %s",
                "FAILED" if bad_status else "SKIPPED",
                status,
                fetch_result.content_type,
                current_url,
            )
            return None

        try:
            page = parse_page(fetch_result.body)
        except Exception as exc:
            logger.error("Failed to parse %s with error %s", current_url, exc)
            self.reject_page(
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
                exclusion_reason="parse_error",
            )
            self.state.statistics.failed += 1
            return None

        if not page.text.strip():
            self.reject_page(
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
                exclusion_reason="empty_text",
                title=page.title,
                token_count=0,
            )
            return None

        # classify before deciding whether to index the page or follow its links
        verdict = classify_page(
            current_url,
            page.title,
            page.text,
            page.language,
            description=page.description,
            h1=page.h1,
            predictor=self.page_critic,
        )
        pageverdict = _pageverdict_metadata(verdict)

        if verdict.should_index:
            # avoids recrawling the same content
            fingerprint = simhash(page.text)
            if page.text and is_near_duplicate(fingerprint, self.seen_texts):
                logger.info("Skipping duplicate text: %s", current_url)
                self.reject_page(
                    current_url=current_url,
                    hostname=hostname,
                    depth=depth,
                    fetch_result=fetch_result,
                    exclusion_reason="duplicate_text",
                    title=page.title,
                    language=verdict.language.value,
                    relevance=verdict.relevance,
                    token_count=verdict.token_count,
                    pageverdict=pageverdict,
                )
                return None
            self.seen_texts.add(fingerprint)

            if not self.save_page(
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
                title=page.title,
                verdict=verdict,
            ):
                return None

            return page.links, verdict.relevance, pageverdict

        index_exclusion = verdict.index_exclusion
        if index_exclusion is not None:
            self.reject_page(
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
                exclusion_reason=index_exclusion.value,
                title=page.title,
                language=verdict.language.value,
                relevance=verdict.relevance,
                token_count=verdict.token_count,
                pageverdict=pageverdict,
            )
        _log_index_exclusion(verdict, fetch_result.status_code, current_url)
        return page.links, verdict.relevance, pageverdict

    def reject_page(
        self,
        *,
        current_url: str,
        hostname: str,
        depth: int,
        fetch_result: FetchResult,
        exclusion_reason: str,
        title: str = "",
        language: str | None = None,
        relevance: float | None = None,
        token_count: int | None = None,
        pageverdict: PageVerdictMetadata | None = None,
    ) -> None:
        self.page_store.upsert_rejected_page(
            title=title,
            url=current_url,
            host=hostname,
            exclusion_reason=exclusion_reason,
            status_code=fetch_result.status_code,
            content_type=fetch_result.content_type,
            crawl_depth=depth,
            language=language,
            relevance=relevance,
            token_count=token_count,
            pageverdict_score=pageverdict.score if pageverdict else None,
            pageverdict_label=pageverdict.label if pageverdict else None,
            pageverdict_decision=pageverdict.decision if pageverdict else None,
            pageverdict_model=pageverdict.model if pageverdict else None,
            pageverdict_snippet=pageverdict.snippet if pageverdict else None,
        )

    def save_page(
        self,
        *,
        current_url: str,
        hostname: str,
        depth: int,
        fetch_result: FetchResult,
        title: str,
        verdict: PageVerdict,
    ) -> bool:
        body = fetch_result.body
        if body is None:
            return False

        try:
            path = save_html(hostname, self.save_dir, current_url, body)
        except Exception as exc:
            logger.error("Failed to save html %s with error %s", current_url, exc)
            self.state.statistics.failed += 1
            return False

        # write crawl information into sqlite db
        self.page_store.upsert_page(
            title=title,
            url=current_url,
            host=hostname,
            path=path,
            status_code=fetch_result.status_code,
            content_type=fetch_result.content_type,
            crawl_depth=depth,
            language=verdict.language.value,
            relevance=verdict.relevance,
            token_count=verdict.token_count,
            pageverdict_score=verdict.score,
            pageverdict_label=verdict.label,
            pageverdict_decision=verdict.decision_label,
            pageverdict_model=verdict.model,
            pageverdict_snippet=verdict.snippet,
        )
        self.state.statistics.saved += 1
        self.host_counts[hostname] = self.host_counts.get(hostname, 0) + 1

        logger.info(
            "%-7s | %3d | rel=%5.1f | %s",
            "SAVED",
            fetch_result.status_code,
            verdict.relevance,
            current_url,
        )
        return True

# caps the number of sites per hostname: goal is to increase entropy by forcing a limit on the crawler
def _host_at_cap(host_counts: dict[str, int], max_pages_per_host: int | None, host: str) -> bool:
    return max_pages_per_host is not None and host_counts.get(host, 0) >= max_pages_per_host


def _pageverdict_metadata(verdict: PageVerdict) -> PageVerdictMetadata:
    return PageVerdictMetadata(
        score=verdict.score,
        label=verdict.label,
        decision=verdict.decision_label,
        model=verdict.model,
        snippet=verdict.snippet,
    )

# add relevant urls on current_url to frontier
def evaluate_links(
    state: CrawlState,
    links: list[tuple[str, str]],
    current_url: str,
    depth: int,
    parent_relevance: float,
    parent_host: str,
    host_counts: dict[str, int],
    max_pages_per_host: int | None,
    link_critic: LinkVerdictPredictor,
    link_store: LinkStore | None = None,
    parent_pageverdict: PageVerdictMetadata | None = None,
) -> None:
    child_depth = depth + 1
    records: list[LinkCandidateRecord] = []
    parent_pageverdict = parent_pageverdict or PageVerdictMetadata(
        score=None,
        label=None,
        decision=None,
        model=None,
        snippet=None,
    )

    for href, anchor in links:
        final_url, is_canonical = canonical_url(href, current_url)
        if not is_canonical or final_url in state.seen_urls:
            continue

        host = normalize_host(urlparse(final_url).hostname)
        verdict = classify_link(
            link_critic,
            anchor=anchor,
            target_url=final_url,
            target_host=host,
            target_depth=child_depth,
            parent_url=current_url,
            parent_host=parent_host,
            parent_depth=depth,
            parent_relevance=parent_relevance,
            parent_score=parent_pageverdict.score,
            parent_decision=parent_pageverdict.decision or "",
        )
        should_enqueue = verdict.enqueue and not _host_at_cap(
            host_counts, max_pages_per_host, host
        )
        records.append(
            LinkCandidateRecord(
                parent_url=current_url,
                parent_host=parent_host,
                parent_depth=depth,
                parent_pageverdict=parent_pageverdict,
                parent_relevance=parent_relevance,
                target_url=final_url,
                target_host=host,
                target_depth=child_depth,
                anchor=anchor,
                raw_score=verdict.frontier_score,
                should_enqueue=should_enqueue,
                selected=should_enqueue,
                rejection_reason=None if should_enqueue else "not_enqueued",
            )
        )
        if should_enqueue:
            push_frontier(
                state,
                verdict.frontier_score,
                final_url,
                child_depth,
                saved_urls_by_host=host_counts,
            )
            # only mark URLs we actually enqueued as seen
            state.seen_urls.add(final_url)

    if link_store is not None:
        link_store.upsert_link_candidates(records)

def _log_index_exclusion(verdict: PageVerdict, status_code: int, url: str) -> None:
    match verdict.index_exclusion:
        case PageIndexExclusion.LOW_PAGEVERDICT_SCORE:
            logger.debug(
                "%-7s | %3d | pv=%0.3f | rel=%5.1f | %s",
                "LOW-PV",
                status_code,
                verdict.score or 0.0,
                verdict.relevance,
                url,
            )
        case PageIndexExclusion.OFF_TOPIC:
            logger.debug(
                "%-7s | %3d | pv=%0.3f | %s",
                "OFFTOPIC",
                status_code,
                verdict.score or 0.0,
                url,
            )
        case PageIndexExclusion.NON_ENGLISH:
            logger.debug(
                "%-7s | %3d | lang=%s | %s",
                "NON-EN",
                status_code,
                verdict.language.value,
                url,
            )
        case None:
            return
