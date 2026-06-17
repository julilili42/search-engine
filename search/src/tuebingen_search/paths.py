from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" 
SEARCH_DIR = PROJECT_ROOT / "search"

DEFAULT_DB_PATH = DATA_DIR / "pages.sqlite"
DEFAULT_INDEX_PATH = PROJECT_ROOT / "index.bin"
DEFAULT_BATCH_PATH = SEARCH_DIR / "queries.tsv"
DEFAULT_RESULT_PATH = SEARCH_DIR / "results.tsv"
