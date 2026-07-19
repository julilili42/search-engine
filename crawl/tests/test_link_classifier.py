from pathlib import Path

from tuebingen_crawler.link_classifier import classify_link
from verdict_ml.base import VerdictPrediction


class FakeLinkPredictor:
    def __init__(self, probability: float, label: str = "positive") -> None:
        self.probability = probability
        self.label = label
        self.seen = []

    def predict(self, example):
        self.seen.append(example)
        return VerdictPrediction(
            label=self.label,
            positive_probability=self.probability,
            model_path=Path("fake_link_verdict.joblib"),
        )


def _classify(predictor, *, url, anchor="Tübingen", depth=1):
    return classify_link(
        predictor,
        anchor=anchor,
        target_url=url,
        target_host="host",
        target_depth=depth,
        parent_url="https://host/",
        parent_host="host",
        parent_depth=depth - 1,
        parent_relevance=5.0,
        parent_score=None,
        parent_decision="",
    )


def test_classify_link_builds_model_input():
    predictor = FakeLinkPredictor(0.7)

    verdict = classify_link(
        predictor,
        anchor="Tübingen tourism",
        target_url="https://www.tuebingen.de/en/visit",
        target_host="www.tuebingen.de",
        target_depth=2,
        parent_url="https://www.tuebingen.de/",
        parent_host="www.tuebingen.de",
        parent_depth=1,
        parent_relevance=6.5,
        parent_score=0.82,
        parent_decision="index_strong",
    )

    assert verdict.score == 0.7
    [example] = predictor.seen
    assert example.anchor == "Tübingen tourism"
    assert example.target_url == "https://www.tuebingen.de/en/visit"
    assert example.target_depth == 2
    assert example.parent_pageverdict_score == 0.82
    assert example.parent_pageverdict_decision == "index_strong"
    assert example.parent_relevance == 6.5


def test_classify_link_enqueues_confident_link():
    verdict = _classify(FakeLinkPredictor(0.9), url="https://host/tuebingen-attractions")

    assert verdict.score == 0.9
    assert verdict.label == "positive"


def test_classify_link_returns_low_scoring_link_verdict():
    verdict = _classify(FakeLinkPredictor(0.01, "negative"), url="https://host/random")

    assert verdict.score == 0.01
    assert verdict.label == "negative"


def test_classify_link_skips_resource_url_without_calling_model():
    predictor = FakeLinkPredictor(0.99)
    verdict = _classify(predictor, url="https://host/image.jpg")

    assert verdict.skipable
    assert predictor.seen == []  # hard skip filter short-circuits before the model


def test_classify_link_preserves_depth():
    verdict = _classify(
        FakeLinkPredictor(0.99),
        url="https://host/tuebingen-attractions",
        depth=99,
    )

    assert verdict.score == 0.99
    assert verdict.depth == 99
