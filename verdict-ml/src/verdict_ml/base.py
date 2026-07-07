from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline


@dataclass(frozen=True)
class VerdictPrediction:
    label: str
    positive_probability: float
    model_path: Path


def build_tfidf_logreg(
    *,
    word_ngram_range: tuple[int, int],
    char_ngram_range: tuple[int, int],
    word_min_df: int = 2,
    word_max_df: float = 0.95,
    char_min_df: int = 2,
    char_max_df: float = 0.98,
    max_iter: int = 2000,
    random_state: int = 13,
) -> Pipeline:
    text_features = FeatureUnion(
        [
            (
                "word",
                TfidfVectorizer(
                    analyzer="word",
                    ngram_range=word_ngram_range,
                    min_df=word_min_df,
                    max_df=word_max_df,
                    sublinear_tf=True,
                    strip_accents="unicode",
                ),
            ),
            (
                "char",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=char_ngram_range,
                    min_df=char_min_df,
                    max_df=char_max_df,
                    sublinear_tf=True,
                    strip_accents="unicode",
                ),
            ),
        ]
    )
    return Pipeline(
        [
            ("features", text_features),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=max_iter,
                    random_state=random_state,
                ),
            ),
        ]
    )


def save_bundle(path: Path, bundle: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, path)


def load_bundle(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(
            f"Verdict model artifact not found: {path}. Train it first with "
            "`uv run verdict-train page` or `uv run verdict-train link`, "
            "or pass an explicit model path."
        )
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or "model" not in bundle:
        raise ValueError(f"Invalid verdict artifact: {path}")
    return bundle


class VerdictPredictor:
    def __init__(self, model_path: Path, make_text: Callable[[object], str]) -> None:
        self.model_path = model_path
        bundle = load_bundle(model_path)
        self.model = bundle["model"]
        self.positive_threshold = float(bundle.get("positive_threshold", 0.5))
        self._make_text = make_text
        self._positive_index = list(self.model.classes_).index("positive")

    def predict_proba(self, example: object) -> float:
        text = self._make_text(example)
        return float(self.model.predict_proba([text])[0][self._positive_index])

    def predict(self, example: object) -> VerdictPrediction:
        probability = self.predict_proba(example)
        label = "positive" if probability >= self.positive_threshold else "negative"
        return VerdictPrediction(
            label=label,
            positive_probability=probability,
            model_path=self.model_path,
        )
