from __future__ import annotations

import logging
from pathlib import Path
from .crawler import crawl, save_jsonl
from .storage import load_seed_toml
from .models import Config

logger = logging.getLogger(__name__)

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    package_dir = Path(__file__).resolve().parent
    crawl_root = package_dir.parent.parent
    seed_path = crawl_root / "seeds.toml"

    sites = load_seed_toml(seed_path)
    print(sites)
    config = Config(sites)
    
    try:
        index = crawl(config)
    except Exception as exc:
        logger.error("Failed to crawl with error %s", exc)
        return

    jsonl_path = Path(config.save_dir) / "index.jsonl"
    try:
        save_jsonl(jsonl_path, index)
    except Exception as exc:
        logger.error("Failed to save jsonl file with error %s", exc)
        return

if __name__ == "__main__":
    main()
