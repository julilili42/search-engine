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
    page = _load_page_model()
    link = _load_link_model()
    return VerdictModels(page=page, link=link)


def _load_page_model() -> PageVerdictPredictor:
    if not DEFAULT_PAGE_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Required PageVerdict model artifact not found: {DEFAULT_PAGE_MODEL_PATH}. "
            "Train it first with `uv run verdict-train page`."
        )

    logger.info("Using PageVerdict model: %s", DEFAULT_PAGE_MODEL_PATH)
    return PageVerdictPredictor()


def _load_link_model() -> LinkVerdictPredictor:
    if not DEFAULT_LINK_MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Required LinkVerdict model artifact not found: {DEFAULT_LINK_MODEL_PATH}. "
            "Train it first with `uv run verdict-train link`."
        )

    logger.info("Using LinkVerdict model: %s", DEFAULT_LINK_MODEL_PATH)
    return LinkVerdictPredictor()
