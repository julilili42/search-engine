from __future__ import annotations

from pathlib import Path
from typing import Dict
from .crawler import crawl, save_jsonl
from .models import Config, Statistics

import httpx


def main() -> None:
    seen_urls: Dict[str, bool] = {}
    config = Config()
    statistics = Statistics()

    headers = {"Accept": config.accept, "User-Agent": config.user_agent}
    client = httpx.Client(timeout=config.request_timeout, headers=headers)

    try:
        index = crawl(client, config.starting_url, seen_urls, config, statistics)
    except Exception as exc:
        print(f"ERROR: failed to crawl with error {exc}")
        return

    jsonl_path = Path(config.save_dir) / "index.jsonl"
    try:
        save_jsonl(jsonl_path, index)
    except Exception as exc:
        print(f"ERROR: failed to save jsonl file with error {exc}")
        return

    statistics.print()


if __name__ == "__main__":
    main()
