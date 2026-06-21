from __future__ import annotations

import logging
from pathlib import Path
from .crawler import crawl_hostname
from .storage import load_seed_toml
from .models import Config
from .save_pages import PageStore
from .paths import DEFAULT_DATA_DIR, DEFAULT_DB_PATH, DEFAULT_SEED_PATH

logger = logging.getLogger(__name__)

# cap saved pages per host
MAX_PAGES_PER_HOST = 60

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    sites = load_seed_toml(DEFAULT_SEED_PATH)
    config = Config(
        sites=sites,
        save_dir=DEFAULT_DATA_DIR,
        max_pages_per_host=MAX_PAGES_PER_HOST,
    )
    
    with PageStore(DEFAULT_DB_PATH) as page_store:
        try:
            crawl_hostname(config, page_store)
        except Exception as exc:
            logger.error("Failed to crawl with error %s", exc)
            return

if __name__ == "__main__":
    main()
