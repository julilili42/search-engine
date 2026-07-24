from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .frontier import (
    saved_host_at_cap,
    host_reject_budget_exhausted,
    GlobalFrontier,
)
from .link_classifier import LinkVerdict, classify_link
from .models import CrawlContext, CrawlLease
from .page_evaluation import PageEvaluation
from .stores import LinkCandidateRecord, PageVerdictMetadata
from .urls import canonical_url, normalize_host

MAX_DEPTH = 5
LINK_SCORE_WEIGHT = 10.0
MAX_SELECTED_LINKS_PER_PAGE = 25
MIN_LINK_SCORE = 0.65


@dataclass(frozen=True)
class _LinkContext:
    current_url: str
    parent_host: str
    parent_depth: int
    child_depth: int
    parent_relevance: float
    parent_pageverdict: PageVerdictMetadata


# frontier admission
def _frontier_score(verdict: LinkVerdict) -> float:
    return LINK_SCORE_WEIGHT * verdict.score


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
    context: CrawlContext,
    ctx: _LinkContext,
    links: list[tuple[str, str]],
) -> tuple[list[tuple[LinkVerdict, str]], list[LinkCandidateRecord]]:
    candidates: list[tuple[LinkVerdict, str]] = []
    records: list[LinkCandidateRecord] = []
    for href, anchor in links:
        final_url, is_canonical = canonical_url(href, ctx.current_url)
        if not is_canonical or final_url in context.state.seen_urls:
            continue

        host = normalize_host(urlparse(final_url).hostname)
        verdict = classify_link(
            context.verdict_models.link,
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
        if (
            verdict.skipable
            or verdict.depth > MAX_DEPTH
            or verdict.score < MIN_LINK_SCORE
            or saved_host_at_cap(context.host_counts, context.config.max_pages_per_host, host)
        ):
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="not_enqueued"))
        elif host_reject_budget_exhausted(
            context.host_counts, context.host_reject_counts, host
        ):
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="host_off_topic"))
        else:
            candidates.append((verdict, anchor))
    return candidates, records


# per-page selection
def _enqueue_best_links(
    ctx: _LinkContext,
    candidates: list[tuple[LinkVerdict, str]],
    frontier: GlobalFrontier,
    lease: CrawlLease,
) -> list[LinkCandidateRecord]:
    records: list[LinkCandidateRecord] = []
    selected_total = 0
    ordered = sorted(
        candidates,
        key=lambda item: _frontier_score(item[0]),
        reverse=True,
    )
    for verdict, anchor in ordered:
        if selected_total >= MAX_SELECTED_LINKS_PER_PAGE:
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="page_total_budget"))
            continue

        enqueued = frontier.submit(
            _frontier_score(verdict), verdict.url, ctx.child_depth, lease.entry.seed_index
        )
        if not enqueued:
            records.append(_link_record(ctx, verdict, anchor, selected=False, reason="already_seen"))
            continue
        selected_total += 1
        records.append(_link_record(ctx, verdict, anchor, selected=True, reason=None))
    return records


# public entrypoint
def evaluate_links(
    context: CrawlContext,
    *,
    page_evaluation: PageEvaluation,
    lease: CrawlLease,
    frontier: GlobalFrontier,
) -> None:
    ctx = _LinkContext(
        current_url=lease.entry.url,
        parent_host=lease.host,
        parent_depth=lease.entry.depth,
        child_depth=lease.entry.depth + 1,
        parent_relevance=page_evaluation.relevance,
        parent_pageverdict=page_evaluation.verdict,
    )

    candidates, records = _classify_candidates(
        context,
        ctx,
        page_evaluation.links,
    )
    records += _enqueue_best_links(
        ctx, candidates, frontier=frontier, lease=lease
    )

    if context.link_store is not None:
        context.link_store.upsert_link_candidates(records)
