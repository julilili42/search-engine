from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .fetcher import fetch_page
from .frontier import CrawlLease, GlobalFrontier, host_reject_budget_exhausted, saved_host_at_cap
from .link_evaluation import evaluate_links
from .models import CrawlSite, CrawlState
from .page_evaluation import evaluate_page
from .save_pages import LinkStore, PageStore
from .sitemap import ingest_sitemaps
from .storage import RobotsCache
from .urls import normalize_host
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


def process_lease(
    context: CrawlContext, site: CrawlSite, frontier: GlobalFrontier, lease: CrawlLease
) -> None:
    """Process one globally scheduled URL and release its host in all cases."""
    current_url, depth = lease.entry.url, lease.entry.depth
    saved = False
    try:
        hostname = normalize_host(urlparse(current_url).hostname)
        with frontier.lock:
            if saved_host_at_cap(context.host_counts, context.max_pages_per_host, hostname):
                return
            if host_reject_budget_exhausted(
                context.host_counts, context.host_reject_counts, hostname
            ):
                return

        if not context.robots.can_fetch(context.user_agent, current_url):
            logger.debug("Skipping disallowed URL: %s", current_url)
            with frontier.lock:
                context.state.statistics.failed += 1
            return

        if site.sitemap and _same_origin(current_url, site.url):
            sitemap_urls = context.robots.site_maps(current_url)
            fallback = not sitemap_urls
            if fallback:
                parsed = urlparse(current_url)
                sitemap_urls = [f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"]
            with frontier.lock:
                pending = sitemap_urls[0] not in context.state.seen_sitemaps
            if pending:
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

        fetch_result = fetch_page(context.client, current_url, site)
        with frontier.lock:
            if fetch_result is None:
                context.state.statistics.failed += 1
                return
            frontier.record_fetch()

            # ponytail: one lock serializes shared crawl state; split it only if model work bottlenecks.
            follow_links = evaluate_page(
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
            if follow_links is None:
                return
            links, relevance, pageverdict = follow_links
            saved = True
            evaluate_links(
                state=context.state,
                links=links,
                current_url=current_url,
                depth=depth,
                parent_relevance=relevance,
                parent_host=hostname,
                host_counts=context.host_counts,
                host_reject_counts=context.host_reject_counts,
                max_pages_per_host=context.max_pages_per_host,
                link_critic=context.link_critic,
                link_store=context.link_store,
                parent_pageverdict=pageverdict,
                frontier=frontier,
                seed_index=lease.entry.seed_index,
            )
    except Exception:
        logger.exception("Failed to process %s", current_url)
        with frontier.lock:
            context.state.statistics.failed += 1
    finally:
        frontier.finish(lease, saved=saved)


def _same_origin(left: str, right: str) -> bool:
    left_parsed, right_parsed = urlparse(left), urlparse(right)
    return (
        left_parsed.scheme == right_parsed.scheme
        and left_parsed.netloc.lower() == right_parsed.netloc.lower()
    )
