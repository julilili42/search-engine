from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from .dedup import is_near_duplicate, simhash
from .extract import parse_page
from .models import CrawlContext, FetchResult
from .page_classifier import PageIndexExclusion, PageVerdict, classify_page
from .stores import PageVerdictMetadata
from .storage import save_html

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageEvaluation:
    links: list[tuple[str, str]]
    relevance: float
    verdict: PageVerdictMetadata


# seen_texts is shared across crawl threads; is_near_duplicate iterates it, so
# check-and-add must be atomic
_SEEN_TEXTS_LOCK = threading.Lock()

def _pageverdict_metadata(verdict: PageVerdict) -> PageVerdictMetadata:
    return PageVerdictMetadata(
        score=verdict.score,
        label=verdict.label,
        decision=verdict.decision_label,
        model=verdict.model,
        snippet=verdict.snippet,
    )


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


def reject_page(
    context: CrawlContext,
    *,
    current_url: str,
    hostname: str,
    depth: int,
    fetch_result: FetchResult,
    exclusion_reason: str,
    title: str = "",
    token_count: int | None = None,
    verdict: PageVerdict | None = None,
) -> None:
    pageverdict = _pageverdict_metadata(verdict) if verdict else None
    token_count = verdict.token_count if verdict else token_count
    context.page_store.upsert_rejected_page(
        title=title,
        url=current_url,
        host=hostname,
        exclusion_reason=exclusion_reason,
        status_code=fetch_result.status_code,
        content_type=fetch_result.content_type,
        crawl_depth=depth,
        language=verdict.language.value if verdict else None,
        relevance=verdict.relevance if verdict else None,
        token_count=token_count,
        pageverdict=pageverdict,
    )
    context.host_reject_counts[hostname] = context.host_reject_counts.get(hostname, 0) + 1
    if context.link_store is not None:
        context.link_store.update_link_target(
            url=current_url,
            target_status="rejected",
            fetch_result=fetch_result,
            verdict=verdict,
            token_count=token_count,
            pageverdict=pageverdict,
            exclusion_reason=exclusion_reason,
        )


def save_page(
    context: CrawlContext,
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
        path = save_html(hostname, context.config.save_dir, current_url, body)
    except Exception as exc:
        logger.error("Failed to save html %s with error %s", current_url, exc)
        context.state.statistics.failed += 1
        return False

    # write crawl information into sqlite db
    context.page_store.upsert_page(
        title=title,
        url=current_url,
        host=hostname,
        path=path,
        crawl_depth=depth,
        fetch_result=fetch_result,
        verdict=verdict,
    )
    context.link_store.update_link_target(
        url=current_url,
        target_status="page",
        fetch_result=fetch_result,
        verdict=verdict,
        exclusion_reason=None,
    )
    context.state.statistics.saved += 1
    context.host_counts[hostname] = context.host_counts.get(hostname, 0) + 1

    logger.info(
        "%-7s | %3d | rel=%5.1f | %s",
        "SAVED",
        fetch_result.status_code,
        verdict.relevance,
        current_url,
    )
    return True

# parse + classify fetched page -> save or reject -> return links to follow for saved page
def evaluate_page(
    context: CrawlContext,
    *,
    current_url: str,
    hostname: str,
    depth: int,
    fetch_result: FetchResult,
) -> PageEvaluation | None:
    if fetch_result.body is None:
        status = fetch_result.status_code
        bad_status = status < 200 or status >= 300
        reject_page(
            context,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            exclusion_reason="bad_status" if bad_status else "non_html",
        )
        if bad_status:
            context.state.statistics.failed += 1
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
        reject_page(
            context,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            exclusion_reason="parse_error",
        )
        context.state.statistics.failed += 1
        return None

    if not page.text.strip():
        reject_page(
            context,
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
        page,
        predictor=context.verdict_models.page,
    )
    pageverdict = _pageverdict_metadata(verdict)

    if verdict.should_index:
        # avoids recrawling the same content
        fingerprint = simhash(page.text)
        with _SEEN_TEXTS_LOCK:
            duplicate = is_near_duplicate(fingerprint, context.state.seen_texts)
            if not duplicate:
                context.state.seen_texts.add(fingerprint)
        if duplicate:
            logger.info("Skipping duplicate text: %s", current_url)
            reject_page(
                context,
                current_url=current_url,
                hostname=hostname,
                depth=depth,
                fetch_result=fetch_result,
                exclusion_reason="duplicate_text",
                title=page.title,
                verdict=verdict,
            )
            return None

        if not save_page(
            context,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            title=page.title,
            verdict=verdict,
        ):
            return None

        return PageEvaluation(page.links, verdict.relevance, pageverdict)

    index_exclusion = verdict.index_exclusion
    if index_exclusion is not None:
        reject_page(
            context,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            exclusion_reason=index_exclusion.value,
            title=page.title,
            verdict=verdict,
        )
    _log_index_exclusion(verdict, fetch_result.status_code, current_url)
    return PageEvaluation(page.links, verdict.relevance, pageverdict)
