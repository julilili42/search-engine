import pytest

import tuebingen_crawler.verdict_models as verdict_models
from tuebingen_crawler.verdict_models import load_verdict_models


def test_load_verdict_models_requires_page_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(
        verdict_models, "DEFAULT_PAGE_MODEL_PATH", tmp_path / "missing.joblib"
    )
    with pytest.raises(FileNotFoundError, match="Required PageVerdict model artifact"):
        load_verdict_models()
