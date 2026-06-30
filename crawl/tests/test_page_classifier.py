from pathlib import Path

from tuebingen_crawler.models import Language
from tuebingen_crawler.page_classifier import (
    CLASSIFIER_CONFIG,
    PageIndexExclusion,
    classify_page,
    page_snippet,
)
from verdict_ml.base import VerdictPrediction


class FakePagePredictor:
    def __init__(self, probability: float, label: str = "positive") -> None:
        self.probability = probability
        self.label = label
        self.seen = []

    def predict(self, example):
        self.seen.append(example)
        return VerdictPrediction(
            label=self.label,
            positive_probability=self.probability,
            model_path=Path("fake.joblib"),
        )


def test_page_snippet_prefers_description_and_h1_before_text():
    snippet = page_snippet(
        description="Official English city page.",
        h1="Tübingen tourism",
        text="Body text " * 100,
    )

    assert snippet.startswith("Official English city page. Tübingen tourism")
    assert len(snippet) <= 700


def test_classify_page_indexes_strong_positive_page():
    verdict = classify_page(
        "https://www.tuebingen.de/en/",
        "Tübingen",
        "English visitor information about Tübingen.",
        Language.EN,
        description="Official English visitor information.",
        predictor=FakePagePredictor(CLASSIFIER_CONFIG.strong_threshold),
    )

    assert verdict.should_index
    assert verdict.index_exclusion is None
    assert verdict.decision_label == "index_strong"
    assert verdict.relevance >= 6.0
    assert verdict.language == "en"
    assert verdict.score == CLASSIFIER_CONFIG.strong_threshold


def test_classify_page_indexes_mid_confidence_page_cautiously():
    verdict = classify_page(
        "https://example.com/tuebingen-directory",
        "Tübingen directory",
        "A narrow directory page.",
        Language.EN,
        predictor=FakePagePredictor(CLASSIFIER_CONFIG.index_threshold),
    )

    assert verdict.should_index
    assert verdict.decision_label == "index_cautious"
    assert verdict.relevance == 3.0


def test_classify_page_rejects_but_still_follows_low_score_page():
    verdict = classify_page(
        "https://example.com/tuebingen-side",
        "Tübingen",
        "A low-scoring page that still mentions Tübingen.",
        Language.EN,
        predictor=FakePagePredictor(CLASSIFIER_CONFIG.index_threshold - 0.01, "negative"),
    )

    assert not verdict.should_index
    assert verdict.index_exclusion is PageIndexExclusion.LOW_PAGEVERDICT_SCORE
    assert verdict.decision_label == "reject_follow"
    assert verdict.relevance < 3.0


def test_classify_page_uses_serp_like_feature_fields():
    predictor = FakePagePredictor(0.8)
    classify_page(
        "https://www.tuebingen.de/en/",
        "Title",
        "Body excerpt.",
        Language.EN,
        description="Meta description.",
        predictor=predictor,
    )

    [example] = predictor.seen
    assert example.title == "Title"
    assert example.url == "https://www.tuebingen.de/en/"
    assert example.display_url == "www.tuebingen.de/en"
    assert example.snippet == "Meta description. Body excerpt."


def test_classify_page_gates_off_topic_page_even_with_high_score():
    # a confidently-scored page that never mentions Tübingen is off-topic drift
    verdict = classify_page(
        "https://www.visit-mv.com/family",
        "Family Vacation at the Baltic Sea in Mecklenburg-Vorpommern",
        "Mecklenburg-Vorpommern offers wide beaches along the Baltic Sea coast.",
        Language.EN,
        predictor=FakePagePredictor(CLASSIFIER_CONFIG.strong_threshold),
    )

    assert not verdict.should_index
    assert verdict.index_exclusion is PageIndexExclusion.OFF_TOPIC


def test_classify_page_indexes_topical_page_without_tuebingen_in_title():
    # Tübingen cue in the body is enough to count as on-topic
    verdict = classify_page(
        "https://example.com/old-town",
        "Old Town",
        "The historic old town sits on the Neckar in Tübingen.",
        Language.EN,
        predictor=FakePagePredictor(CLASSIFIER_CONFIG.strong_threshold),
    )

    assert verdict.should_index
    assert verdict.index_exclusion is None


def test_classify_page_rejects_non_english_page():
    verdict = classify_page(
        "https://www.tuebingen.de/de/",
        "Tübingen",
        "Tübingen ist eine Universitätsstadt am Neckar.",
        Language.DE,
        predictor=FakePagePredictor(CLASSIFIER_CONFIG.strong_threshold),
    )

    assert not verdict.should_index
    assert verdict.index_exclusion is PageIndexExclusion.NON_ENGLISH
