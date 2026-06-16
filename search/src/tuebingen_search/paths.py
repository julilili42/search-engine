from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent.parent

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "pages.sqlite"
DEFAULT_INDEX_PATH = PROJECT_ROOT / "index.bin"