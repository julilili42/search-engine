from __future__ import annotations

import logging
from dataclasses import dataclass

from verdict_ml.link.predict import (
    DEFAULT_MODEL_PATH as DEFAULT_LINK_MODEL_PATH,
    LinkVerdictPredictor,
)
from verdict_ml.page.predict import (
    DEFAULT_MODEL_PATH as DEFAULT_PAGE_MODEL_PATH,
    PageVerdictPredictor,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VerdictModels:
    page: PageVerdictPredictor
    link: LinkVerdictPredictor


def load_verdict_models() -> VerdictModels:
    return VerdictModels(page=_load_page_model(), link=_load_link_model())


def _load_page_model() -> PageVerdictPredictor:
    model_path = DEFAULT_PAGE_MODEL_PATH
    if not model_path.exists():
        raise FileNotFoundError(
            f"Required PageVerdict model artifact not found: {model_path}. "
            "Copy a tested PageVerdict release from labeling-lab."
        )

    logger.info("Using PageVerdict model: %s", model_path)
    return PageVerdictPredictor(model_path)


def _load_link_model() -> LinkVerdictPredictor:
    model_path = DEFAULT_LINK_MODEL_PATH
    if not model_path.exists():
        raise FileNotFoundError(
            f"Required LinkVerdict model artifact not found: {model_path}. "
            "Copy a tested LinkVerdict release from labeling-lab."
        )

    logger.info("Using LinkVerdict model: %s", model_path)
    return LinkVerdictPredictor(model_path)
