from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .frontier import (
    ENQUEUE_FLOOR,
    LINK_SCORE_WEIGHT,
    MAX_DEPTH,
    saved_host_at_cap,
    host_reject_budget_exhausted,
    GlobalFrontier,
)
from .link_classifier import LinkVerdict, classify_link
from .models import CrawlState
from .save_pages import LinkCandidateRecord, LinkStore, PageVerdictMetadata
from .urls import canonical_url, normalize_host
from verdict_ml.link.predict import LinkVerdictPredictor

# per-page selection budgets
MAX_SELECTED_LINKS_PER_URL_FAMILY = 6
MAX_SELECTED_LINKS_PER_TARGET_HOST = 16
HIGH_CONFIDENCE_LINK_SCORE = 0.50

_LANGUAGE_SEGMENTS = {"en", "eng", "english", "de", "deutsch", "german"}


@dataclass(frozen=True)
class _LinkContext:
    current_url: str
    parent_host: str
    parent_depth: int
    child_depth: int
    parent_relevance: float
    parent_pageverdict: PageVerdictMetadata


# link grouping
# group url by host and website path segment, language prefix is transparent
# /en/news/a      => ("example.com", "en", "news")
# /en/news/b      => ("example.com", "en", "news")
# en is ignored and both urls are in the same url family
def _url_family(url: str) -> tuple[str, str, str]:
    parsed = urlparse(url)
    host = normalize_host(parsed.hostname)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    first = segments[0].lower() if len(segments) >= 1 else ""
    second = segments[1].lower() if len(segments) >= 2 else ""
    if first in _LANGUAGE_SEGMENTS:
        return host, first, second
    return host, first, ""


# frontier admission
def _frontier_score(verdict: LinkVerdict) -> float:
    return LINK_SCORE_WEIGHT * verdict.score


def _can_enter_frontier(verdict: LinkVerdict) -> bool:
    return (
        not verdict.skipable
        and verdict.score >= ENQUEUE_FLOOR
        and verdict.depth <= MAX_DEPTH
    )


# record building
def _link_record(
    ctx: _LinkContext, verdict: LinkVerdict, anchor: str, *, selected: bool, reason: str | None
) -> LinkCandidateRecord:
    return LinkCandidateRecord(
        parent_url=ctx.current_url,
        parent_host=ctx.parent_host,
        parent_depth=ctx.parent_depth,
        parent_pageverdict=ctx.parent_pageverdict,
        parent_relevance=ctx.parent_relevance,
        target_url=verdict.url,
        target_host=normalize_host(urlparse(verdict.url).hostname),
        target_depth=ctx.child_depth,
        anchor=anchor,
        raw_score=_frontier_score(verdict),
        # skipped links never reached the model, verdict is empty
        linkverdict_score=None if verdict.skipable else verdict.score,
        linkverdict_label=None if verdict.skipable else verdict.label,
        linkverdict_model=None if verdict.skipable else verdict.model,
        should_enqueue=reason not in {"not_enqueued", "host_off_topic"},
        selected=selected,
        rejection_reason=reason,
    )


# candidate filtering
def _classify_candidates(
    ctx: _LinkContext,
    links: list[tuple[str, str]],
    state: CrawlState,
    host_counts: dict[str, int],
    host_reject_counts: dict[str, int],
    max_pages_per_host: int | None,
    link_critic: LinkVerdictPredictor,
) -> tuple[list[tuple[LinkVerdict, str]], list[LinkCandidateRecord]]:
    candidates: list[tuple[LinkVerdict, str]] = []
    records: list[LinkCandidateRecord] = []
    for href, anchor in links:
        final_url, is_canonical = canonical_url(href, ctx.current_url)
        if not is_canonical or final_url in state.seen_urls:
            continue

        host = normalize_host(urlparse(final_url).hostname)
        verdict = classify_link(
            link_critic,
            anchor=anchor,
            target_url=final_url,
            target_host=host,
            target_depth=ctx.child_depth,
            parent_url=ctx.current_url,
            parent_host=ctx.parent_host,
            parent_depth=ctx.parent_depth,
            parent_relevance=ctx.parent_relevance,
            parent_score=ctx.parent_pageverdict.score,
            parent_decision=ctx.parent_pageverdict.decision or "",
        )
        if not _can_enter_frontier(verdict) or saved_host_at_cap(
            host_counts, max_pages_per_host, host
        ):
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="not_enqueued"))
        elif host_reject_budget_exhausted(host_counts, host_reject_counts, host):
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="host_off_topic"))
        else:
            candidates.append((verdict, anchor))
    return candidates, records


# per-page selection
def _enqueue_with_page_caps(
    ctx: _LinkContext,
    candidates: list[tuple[LinkVerdict, str]],
    frontier: GlobalFrontier,
    seed_index: int,
) -> list[LinkCandidateRecord]:
    records: list[LinkCandidateRecord] = []
    selected_links_by_host: dict[str, int] = {}
    selected_links_by_family: dict[tuple[str, str, str], int] = {}
    for verdict, anchor in sorted(
        candidates, key=lambda item: _frontier_score(item[0]), reverse=True
    ):
        host = normalize_host(urlparse(verdict.url).hostname)
        if selected_links_by_host.get(host, 0) >= MAX_SELECTED_LINKS_PER_TARGET_HOST:
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="page_host_budget"))
            continue

        family = _url_family(verdict.url)
        family_limit = MAX_SELECTED_LINKS_PER_URL_FAMILY + int(
            verdict.score >= HIGH_CONFIDENCE_LINK_SCORE
        )
        if selected_links_by_family.get(family, 0) >= family_limit:
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="page_family_budget"))
            continue

        enqueued = frontier.submit(
            _frontier_score(verdict), verdict.url, ctx.child_depth, seed_index
        )
        if not enqueued:
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="already_seen"))
            continue
        selected_links_by_host[host] = selected_links_by_host.get(host, 0) + 1
        selected_links_by_family[family] = selected_links_by_family.get(family, 0) + 1
        records.append(_link_record(ctx, verdict, anchor, selected=True, reason=None))
    return records


# public entrypoint
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
    frontier: GlobalFrontier,
    seed_index: int,
    host_reject_counts: dict[str, int] | None = None,
    link_store: LinkStore | None = None,
    parent_pageverdict: PageVerdictMetadata | None = None,
) -> None:
    ctx = _LinkContext(
        current_url=current_url,
        parent_host=parent_host,
        parent_depth=depth,
        child_depth=depth + 1,
        parent_relevance=parent_relevance,
        parent_pageverdict=parent_pageverdict
        or PageVerdictMetadata(score=None, label=None, decision=None, model=None, snippet=None),
    )

    candidates, records = _classify_candidates(
        ctx, links, state, host_counts, host_reject_counts or {}, max_pages_per_host, link_critic
    )
    records += _enqueue_with_page_caps(
        ctx, candidates, frontier=frontier, seed_index=seed_index
    )

    if link_store is not None:
        link_store.upsert_link_candidates(records)
