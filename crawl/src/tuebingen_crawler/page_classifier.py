from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from verdict_ml.page.features import PageVerdictInput

from .models import Language
@dataclass(frozen=True)
class PageClassifierConfig:
    index_threshold: float = 0.70
    strong_threshold: float = 0.80
    snippet_max_chars: int = 700


CLASSIFIER_CONFIG = PageClassifierConfig()


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
    english: bool = True

    @property
    def should_index(self) -> bool:
        return self.english and self.score >= CLASSIFIER_CONFIG.index_threshold

    @property
    def decision_label(self) -> PageDecision:
        if self.score >= CLASSIFIER_CONFIG.strong_threshold:
            return PageDecision.INDEX_STRONG
        if self.score >= CLASSIFIER_CONFIG.index_threshold:
            return PageDecision.INDEX_CAUTIOUS
        return PageDecision.REJECT_FOLLOW

    @property
    def index_exclusion(self) -> PageIndexExclusion | None:
        if self.should_index:
            return None
        if not self.english:
            return PageIndexExclusion.NON_ENGLISH
        if self.score < CLASSIFIER_CONFIG.index_threshold:
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
    return collapsed[:CLASSIFIER_CONFIG.snippet_max_chars]


def _strip_scheme(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").strip("/")


def _relevance(score: float) -> float:
    if score >= CLASSIFIER_CONFIG.strong_threshold:
        return 6.0 + 4.0 * ((score - CLASSIFIER_CONFIG.strong_threshold) / (1.0 - CLASSIFIER_CONFIG.strong_threshold))
    if score >= CLASSIFIER_CONFIG.index_threshold:
        return 3.0 + 2.0 * ((score - CLASSIFIER_CONFIG.index_threshold) / (CLASSIFIER_CONFIG.strong_threshold - CLASSIFIER_CONFIG.index_threshold))
    return 2.0 * (score / CLASSIFIER_CONFIG.index_threshold)


def classify_page(
    url: str,
    title: str,
    text: str,
    language: Language,
    *,
    description: str = "",
    h1: str = "",
    predictor,
) -> PageVerdict:
    snippet = page_snippet(description=description, h1=h1, text=text)
    prediction = predictor.predict(
        PageVerdictInput(
            title=title,
            url=url,
            display_url=_strip_scheme(url),
            # model was trained on serp snippets, so keep the page text out of snippet
            snippet=page_snippet(description=description, h1=h1),
            text=text,
        )
    )
    score = prediction.positive_probability
    return PageVerdict(
        language=language,
        relevance=_relevance(score),
        token_count=_token_count(text),
        score=score,
        label=prediction.label,
        model=str(prediction.model_path),
        snippet=snippet,
        english=language == Language.EN,
    )
