from __future__ import annotations

from dataclasses import dataclass

from verdict_ml.link.features import LinkVerdictInput, is_skipable_link
from verdict_ml.link.predict import LinkVerdictPredictor


@dataclass(frozen=True)
class LinkVerdict:
    url: str
    depth: int
    score: float  # model positive_probability
    label: str
    model: str
    skipable: bool

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

    prediction = predictor.predict(
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
    return LinkVerdict(
        url=target_url,
        depth=target_depth,
        score=prediction.positive_probability,
        label=prediction.label,
        model=str(prediction.model_path),
        skipable=False,
    )
