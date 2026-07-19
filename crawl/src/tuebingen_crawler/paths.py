from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CRAWL_ROOT = PACKAGE_DIR.parent.parent
PROJECT_ROOT = CRAWL_ROOT.parent

DEFAULT_SEED_PATH = CRAWL_ROOT / "seeds.toml"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def crawl_paths(data_dir: Path) -> tuple[Path, Path, Path]:
    return (
        data_dir / "html",
        data_dir / "db" / "pages.sqlite",
        data_dir / "log" / "crawl.log",
    )


def global_frontier_state_path(state_dir: Path) -> Path:
    return state_dir / "state" / "global_frontier.json"


def global_seen_state_path(state_dir: Path) -> Path:
    return state_dir / "state" / "global_seen.json"


DEFAULT_DB_PATH = DEFAULT_DATA_DIR / "db" / "pages.sqlite"
