from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ML_ROOT = PACKAGE_DIR.parent.parent
REPO_ROOT = ML_ROOT.parent

ARTIFACTS_DIR = ML_ROOT / "artifacts"
