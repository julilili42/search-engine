from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .fetcher import fetch_bytes
from .frontier import GlobalFrontier, host_reject_budget_exhausted, saved_host_at_cap
from .link_evaluation import evaluate_links
from .models import CrawlLease, CrawlSite, CrawlState, FetchResult
from .page_evaluation import PageEvaluation, evaluate_page
from .stores import LinkStore, PageStore
from .sitemap import ingest_sitemaps
from .storage import RobotsCache
from .urls import normalize_host, same_origin
from verdict_ml.link.predict import LinkVerdictPredictor
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)


@dataclass
class CrawlContext:
    client: httpx.Client
    state: CrawlState
    page_store: PageStore
    link_store: LinkStore
    robots: RobotsCache
    user_agent: str
    save_dir: Path
    host_counts: dict[str, int]
    host_reject_counts: dict[str, int]
    max_pages_per_host: int | None
    page_critic: PageVerdictPredictor
    link_critic: LinkVerdictPredictor

# Process one claimed URL and always release its host.
def process_claimed_lease(
    context: CrawlContext, site: CrawlSite | None, frontier: GlobalFrontier, lease: CrawlLease
) -> None:
    current_url, depth = lease.entry.url, lease.entry.depth
    saved = False
    cooldown_seconds = 0.0
    try:
        if site is None:
            logger.warning("Dropping frontier entry for removed seed %s", lease.entry.seed_index)
            return

        hostname = normalize_host(urlparse(current_url).hostname)
        if not _host_has_budget(context, frontier, hostname):
            return

        if not context.robots.can_fetch(context.user_agent, current_url):
            logger.debug("Skipping disallowed URL: %s", current_url)
            with frontier.lock:
                context.state.statistics.failed += 1
            return

        _ingest_site_sitemap(context, site, frontier, lease, current_url)
        try:
            fetch_result = fetch_bytes(
                context.client,
                current_url,
                request_timeout=site.request_timeout,
                retry_delay=site.retry_delay,
                retries=site.retries,
            )
        except Exception:
            logger.error("%-7s | %-3s | %-5.1s | %s", "FAILED", "-", "-", current_url)
            fetch_result = None
        with frontier.lock:
            page_evaluation, cooldown_seconds = _evaluate_fetch_result(
                context, frontier, current_url, hostname, depth, fetch_result
            )
            if page_evaluation is None:
                return
            saved = True
            _process_links(
                context, frontier, lease, current_url, hostname, depth, page_evaluation
            )
    except Exception:
        logger.exception("Failed to process %s", current_url)
        with frontier.lock:
            context.state.statistics.failed += 1
    finally:
        frontier.finish(lease, saved=saved, cooldown_seconds=cooldown_seconds)


def _evaluate_fetch_result(
    context: CrawlContext,
    frontier: GlobalFrontier,
    current_url: str,
    hostname: str,
    depth: int,
    fetch_result: FetchResult | None,
) -> tuple[PageEvaluation | None, float]:
    if fetch_result is None:
        context.state.statistics.failed += 1
        return None, 0.0
    if fetch_result.cooldown_seconds:
        context.state.statistics.failed += 1
        return None, fetch_result.cooldown_seconds
    frontier.record_fetch()

    page_evaluation = evaluate_page(
        page_store=context.page_store,
        link_store=context.link_store,
        save_dir=context.save_dir,
        seen_texts=context.state.seen_texts,
        host_counts=context.host_counts,
        host_reject_counts=context.host_reject_counts,
        state=context.state,
        page_critic=context.page_critic,
        current_url=current_url,
        hostname=hostname,
        depth=depth,
        fetch_result=fetch_result,
    )
    if page_evaluation is None:
        return None, 0.0
    return page_evaluation, 0.0


def _process_links(
    context: CrawlContext,
    frontier: GlobalFrontier,
    lease: CrawlLease,
    current_url: str,
    hostname: str,
    depth: int,
    page_evaluation: PageEvaluation,
) -> None:
    evaluate_links(
        state=context.state,
        links=page_evaluation.links,
        current_url=current_url,
        depth=depth,
        parent_relevance=page_evaluation.relevance,
        parent_host=hostname,
        host_counts=context.host_counts,
        host_reject_counts=context.host_reject_counts,
        max_pages_per_host=context.max_pages_per_host,
        link_critic=context.link_critic,
        link_store=context.link_store,
        parent_pageverdict=page_evaluation.verdict,
        frontier=frontier,
        seed_index=lease.entry.seed_index,
    )


# Check host page and reject budgets.
def _host_has_budget(context: CrawlContext, frontier: GlobalFrontier, hostname: str) -> bool:
    with frontier.lock:
        return not saved_host_at_cap(
            context.host_counts, context.max_pages_per_host, hostname
        ) and not host_reject_budget_exhausted(
            context.host_counts, context.host_reject_counts, hostname
        )


# Ingest a same-origin sitemap once when the seed opts in.
def _ingest_site_sitemap(
    context: CrawlContext,
    site: CrawlSite,
    frontier: GlobalFrontier,
    lease: CrawlLease,
    current_url: str,
) -> None:
    if not site.sitemap or not same_origin(current_url, site.url):
        return

    sitemap_urls = context.robots.site_maps(current_url)
    fallback = not sitemap_urls
    parsed = urlparse(current_url)
    if fallback:
        sitemap_urls = [f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"]
    with frontier.lock:
        pending = sitemap_urls[0] not in context.state.seen_sitemaps
    if not pending:
        return

    queued = ingest_sitemaps(
        context.client,
        sitemap_urls,
        current_url,
        context.state,
        frontier,
        lease.entry.seed_index,
        site.request_delay,
        site.request_timeout,
    )
    if fallback and not queued:
        logger.info("No sitemap URLs found for %s", parsed.netloc)
