from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import joblib


@dataclass(frozen=True)
class VerdictPrediction:
    label: str
    positive_probability: float
    model_path: Path


def load_bundle(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(
            f"Verdict model artifact not found: {path}. Train it first with "
            "Copy a tested release from labeling-lab, or pass an explicit model path."
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
