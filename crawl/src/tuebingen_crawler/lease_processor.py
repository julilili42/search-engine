from __future__ import annotations

import logging
from urllib.parse import urlparse

from .fetcher import fetch_bytes
from .frontier import GlobalFrontier, host_reject_budget_exhausted, saved_host_at_cap
from .link_evaluation import evaluate_links
from .models import CrawlContext, CrawlLease, CrawlSite, CrawlState
from .page_evaluation import evaluate_page
from .urls import normalize_host

logger = logging.getLogger(__name__)


# Process one claimed URL and always release its host.
def process_claimed_lease(
    context: CrawlContext, site: CrawlSite | None, frontier: GlobalFrontier, lease: CrawlLease
) -> None:
    current_url, depth = lease.entry.url, lease.entry.depth
    cooldown_seconds = 0.0
    try:
        if site is None:
            logger.warning("Dropping frontier entry for removed seed %s", lease.entry.seed_index)
            return

        hostname = normalize_host(urlparse(current_url).hostname)
        if not _host_has_budget(context, frontier, hostname):
            return

        if not context.robots.can_fetch(context.config.user_agent, current_url):
            logger.debug("Skipping disallowed URL: %s", current_url)
            with frontier.lock:
                context.state.statistics.failed += 1
            return

        try:
            fetch_result = fetch_bytes(
                context.client,
                current_url,
                request_timeout=context.config.request_timeout,
                retry_delay=context.config.retry_delay,
                retries=context.config.retries,
            )
        except Exception:
            logger.error("%-7s | %-3s | %-5.1s | %s", "FAILED", "-", "-", current_url)
            fetch_result = None
        with frontier.lock:
            if fetch_result is None:
                context.state.statistics.failed += 1
                return
            if fetch_result.cooldown_seconds:
                context.state.statistics.failed += 1
                cooldown_seconds = fetch_result.cooldown_seconds
                return
            frontier.record_fetch()
            page_evaluation = evaluate_page(
                context,
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
            )
            if page_evaluation is None:
                return
            evaluate_links(
                context,
                page_evaluation=page_evaluation,
                lease=lease,
                frontier=frontier,
            )
    except Exception:
        logger.exception("Failed to process %s", current_url)
        with frontier.lock:
            context.state.statistics.failed += 1
    finally:
        frontier.finish(lease, cooldown_seconds=cooldown_seconds)


# Check host page and reject budgets.
def _host_has_budget(context: CrawlContext, frontier: GlobalFrontier, hostname: str) -> bool:
    with frontier.lock:
        return not saved_host_at_cap(
            context.host_counts, context.config.max_pages_per_host, hostname
        ) and not host_reject_budget_exhausted(
            context.host_counts, context.host_reject_counts, hostname
        )
