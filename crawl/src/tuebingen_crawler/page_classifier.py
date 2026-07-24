from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from verdict_ml.page.features import PageVerdictInput

from .extract import ParsedPage
from .models import Language


INDEX_THRESHOLD = 0.40090708816674747
STRONG_THRESHOLD = 0.80
SNIPPET_MAX_CHARS = 700


class PageIndexExclusion(StrEnum):
    LOW_PAGEVERDICT_SCORE = "low_pageverdict_score"
    NON_ENGLISH = "non_english"


class PageDecision(StrEnum):
    INDEX_STRONG = "index_strong"
    INDEX_CAUTIOUS = "index_cautious"
    REJECT_FOLLOW = "reject_follow"


@dataclass(frozen=True)
class PageVerdict:
    language: Language
    relevance: float
    token_count: int
    score: float
    label: str
    model: str
    snippet: str

    @property
    def should_index(self) -> bool:
        return self.language is Language.EN and self.score >= INDEX_THRESHOLD

    @property
    def decision_label(self) -> PageDecision:
        if self.score >= STRONG_THRESHOLD:
            return PageDecision.INDEX_STRONG
        if self.score >= INDEX_THRESHOLD:
            return PageDecision.INDEX_CAUTIOUS
        return PageDecision.REJECT_FOLLOW

    @property
    def index_exclusion(self) -> PageIndexExclusion | None:
        if self.should_index:
            return None
        if self.language is not Language.EN:
            return PageIndexExclusion.NON_ENGLISH
        if self.score < INDEX_THRESHOLD:
            return PageIndexExclusion.LOW_PAGEVERDICT_SCORE
        return None


def _token_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def page_snippet(description: str = "", h1: str = "", text: str = "") -> str:
    parts: list[str] = []
    if description.strip():
        parts.append(description)
    if h1.strip() and h1.strip() not in description:
        parts.append(h1)
    if text.strip():
        parts.append(text)
    collapsed = " ".join(" ".join(parts).split())
    return collapsed[:SNIPPET_MAX_CHARS]


def _strip_scheme(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").strip("/")


def _relevance(score: float) -> float:
    if score >= STRONG_THRESHOLD:
        return 6.0 + 4.0 * ((score - STRONG_THRESHOLD) / (1.0 - STRONG_THRESHOLD))
    if score >= INDEX_THRESHOLD:
        return 3.0 + 2.0 * ((score - INDEX_THRESHOLD) / (STRONG_THRESHOLD - INDEX_THRESHOLD))
    return 2.0 * (score / INDEX_THRESHOLD)


def classify_page(
    url: str,
    page: ParsedPage,
    *,
    predictor,
) -> PageVerdict:
    snippet = page_snippet(description=page.description, h1=page.h1, text=page.text)
    prediction = predictor.predict(
        PageVerdictInput(
            title=page.title,
            url=url,
            display_url=_strip_scheme(url),
            # model was trained on serp snippets, so keep the page text out of snippet
            snippet=page_snippet(description=page.description, h1=page.h1),
            text=page.text,
        )
    )
    score = prediction.positive_probability
    return PageVerdict(
        language=page.language,
        relevance=_relevance(score),
        token_count=_token_count(page.text),
        score=score,
        label=prediction.label,
        model=str(prediction.model_path),
        snippet=snippet,
    )
