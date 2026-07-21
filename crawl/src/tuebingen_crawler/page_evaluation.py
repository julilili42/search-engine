from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .dedup import is_near_duplicate, simhash
from .extract import parse_page
from .models import CrawlState, FetchResult
from .page_classifier import PageIndexExclusion, PageVerdict, classify_page
from .stores import LinkStore, PageStore, PageVerdictMetadata
from .storage import save_html
from verdict_ml.page.predict import PageVerdictPredictor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PageEvaluation:
    links: list[tuple[str, str]]
    relevance: float
    verdict: PageVerdictMetadata
    saved: bool


# seen_texts is shared across crawl threads; is_near_duplicate iterates it, so
# check-and-add must be atomic
_SEEN_TEXTS_LOCK = threading.Lock()

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    *,
    page_store: PageStore,
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
    host_reject_counts: dict[str, int] | None = None,
    link_store: LinkStore | None = None,
) -> None:
    page_store.upsert_rejected_page(
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
    if host_reject_counts is not None:
        host_reject_counts[hostname] = host_reject_counts.get(hostname, 0) + 1
    if link_store is not None:
        link_store.update_link_target(
            url=current_url,
            target_status="rejected",
            status_code=fetch_result.status_code,
            content_type=fetch_result.content_type,
            language=language,
            relevance=relevance,
            token_count=token_count,
            pageverdict_score=pageverdict.score if pageverdict else None,
            pageverdict_label=pageverdict.label if pageverdict else None,
            pageverdict_decision=pageverdict.decision if pageverdict else None,
            exclusion_reason=exclusion_reason,
            fetched_at=_now(),
        )


def save_page(
    *,
    page_store: PageStore,
    link_store: LinkStore,
    save_dir: Path,
    state: CrawlState,
    host_counts: dict[str, int],
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
        path = save_html(hostname, save_dir, current_url, body)
    except Exception as exc:
        logger.error("Failed to save html %s with error %s", current_url, exc)
        state.statistics.failed += 1
        return False

    # write crawl information into sqlite db
    page_store.upsert_page(
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
    link_store.update_link_target(
        url=current_url,
        target_status="page",
        status_code=fetch_result.status_code,
        content_type=fetch_result.content_type,
        language=verdict.language.value,
        relevance=verdict.relevance,
        token_count=verdict.token_count,
        pageverdict_score=verdict.score,
        pageverdict_label=verdict.label,
        pageverdict_decision=verdict.decision_label,
        exclusion_reason=None,
        fetched_at=_now(),
    )
    state.statistics.saved += 1
    host_counts[hostname] = host_counts.get(hostname, 0) + 1

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
    *,
    page_store: PageStore,
    link_store: LinkStore,
    save_dir: Path,
    seen_texts: set[int],
    host_counts: dict[str, int],
    host_reject_counts: dict[str, int],
    state: CrawlState,
    page_critic: PageVerdictPredictor,
    current_url: str,
    hostname: str,
    depth: int,
    fetch_result: FetchResult,
) -> PageEvaluation | None:
    if fetch_result.body is None:
        status = fetch_result.status_code
        bad_status = status < 200 or status >= 300
        reject_page(
            page_store=page_store,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            exclusion_reason="bad_status" if bad_status else "non_html",
            host_reject_counts=host_reject_counts,
            link_store=link_store,
        )
        if bad_status:
            state.statistics.failed += 1
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
            page_store=page_store,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            exclusion_reason="parse_error",
            host_reject_counts=host_reject_counts,
            link_store=link_store,
        )
        state.statistics.failed += 1
        return None

    if not page.text.strip():
        reject_page(
            page_store=page_store,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            exclusion_reason="empty_text",
            title=page.title,
            token_count=0,
            host_reject_counts=host_reject_counts,
            link_store=link_store,
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
        predictor=page_critic,
    )
    pageverdict = _pageverdict_metadata(verdict)

    if verdict.should_index:
        # avoids recrawling the same content
        fingerprint = simhash(page.text)
        with _SEEN_TEXTS_LOCK:
            duplicate = is_near_duplicate(fingerprint, seen_texts)
            if not duplicate:
                seen_texts.add(fingerprint)
        if duplicate:
            logger.info("Skipping duplicate text: %s", current_url)
            reject_page(
                page_store=page_store,
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
                host_reject_counts=host_reject_counts,
                link_store=link_store,
            )
            return None

        if not save_page(
            page_store=page_store,
            link_store=link_store,
            save_dir=save_dir,
            state=state,
            host_counts=host_counts,
            current_url=current_url,
            hostname=hostname,
            depth=depth,
            fetch_result=fetch_result,
            title=page.title,
            verdict=verdict,
        ):
            return None

        return PageEvaluation(page.links, verdict.relevance, pageverdict, saved=True)

    index_exclusion = verdict.index_exclusion
    if index_exclusion is not None:
        reject_page(
            page_store=page_store,
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
            host_reject_counts=host_reject_counts,
            link_store=link_store,
        )
    _log_index_exclusion(verdict, fetch_result.status_code, current_url)
    return PageEvaluation(page.links, verdict.relevance, pageverdict, saved=False)
