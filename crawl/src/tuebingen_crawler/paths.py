from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CRAWL_ROOT = PACKAGE_DIR.parent.parent
PROJECT_ROOT = CRAWL_ROOT.parent

DEFAULT_SEED_PATH = CRAWL_ROOT / "seeds.toml"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_HTML_DIR = DEFAULT_DATA_DIR / "html"
DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "pages.sqlite"
