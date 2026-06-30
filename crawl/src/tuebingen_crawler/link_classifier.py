from __future__ import annotations

from dataclasses import dataclass

from verdict_ml.link.features import LinkVerdictInput, is_skipable_link
from verdict_ml.link.predict import LinkVerdictPrediction, LinkVerdictPredictor


@dataclass(frozen=True)
class FrontierConfig:
    # a link is enqueued once the model is at least this confident
    enqueue_floor: float = 0.35
    max_depth: int = 5

    def within_depth(self, depth: int) -> bool:
        return depth <= self.max_depth


FRONTIER_CONFIG = FrontierConfig()


@dataclass(frozen=True)
class LinkVerdict:
    url: str
    depth: int
    score: float  # model positive_probability
    label: str
    model: str
    skipable: bool

    @property
    def frontier_score(self) -> float:
        # lift the 0..1 probability onto the same scale as the frontier's
        # depth/host penalties so model confidence still drives ordering
        return 10.0 * self.score

    @property
    def enqueue(self) -> bool:
        return (
            not self.skipable
            and self.score >= FRONTIER_CONFIG.enqueue_floor
            and FRONTIER_CONFIG.within_depth(self.depth)
        )


def predict_link(
    predictor: LinkVerdictPredictor,
    *,
    anchor: str,
    target_url: str,
    target_host: str,
    target_depth: int,
    parent_url: str,
    parent_host: str,
    parent_depth: int,
    parent_relevance: float | None,
    parent_score: float | None,
    parent_decision: str,
) -> LinkVerdictPrediction:
    return predictor.predict(
        LinkVerdictInput(
            anchor=anchor,
            target_url=target_url,
            target_host=target_host,
            target_depth=target_depth,
            parent_url=parent_url,
            parent_host=parent_host,
            parent_depth=parent_depth,
            parent_relevance=parent_relevance,
            parent_pageverdict_score=parent_score,
            parent_pageverdict_decision=parent_decision,
        )
    )


def classify_link(
    predictor: LinkVerdictPredictor,
    *,
    anchor: str,
    target_url: str,
    target_host: str,
    target_depth: int,
    parent_url: str,
    parent_host: str,
    parent_depth: int,
    parent_relevance: float | None,
    parent_score: float | None,
    parent_decision: str,
) -> LinkVerdict:
    # the hard skip filter runs before the model so obvious junk costs no prediction
    if is_skipable_link(target_url):
        return LinkVerdict(
            url=target_url, depth=target_depth, score=0.0, label="", model="", skipable=True
        )

    prediction = predict_link(
        predictor,
        anchor=anchor,
        target_url=target_url,
        target_host=target_host,
        target_depth=target_depth,
        parent_url=parent_url,
        parent_host=parent_host,
        parent_depth=parent_depth,
        parent_relevance=parent_relevance,
        parent_score=parent_score,
        parent_decision=parent_decision,
    )
    return LinkVerdict(
        url=target_url,
        depth=target_depth,
        score=prediction.positive_probability,
        label=prediction.label,
        model=str(prediction.model_path),
        skipable=False,
    )
