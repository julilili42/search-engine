from __future__ import annotations

import logging
from pathlib import Path
from .crawler import crawl_hostname
from .storage import load_seed_toml
from .models import Config
from .page_store import PageStore

logger = logging.getLogger(__name__)

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    package_dir = Path(__file__).resolve().parent
    crawl_root = package_dir.parent.parent
    project_root = crawl_root.parent

    seed_path = crawl_root / "seeds.toml"
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "pages.sqlite"
    sites = load_seed_toml(seed_path)
    config = Config(sites=sites, save_dir=data_dir)
    
    with PageStore(db_path) as page_store:
        try:
            crawl_hostname(config, page_store)
        except Exception as exc:
            logger.error("Failed to crawl with error %s", exc)
            return

if __name__ == "__main__":
    main()
