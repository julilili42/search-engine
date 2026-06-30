from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from collections.abc import Sequence

from .report import report_main
from .scheduler import crawl_hostname
from .storage import load_seed_toml
from .models import Config
from .save_pages import LinkStore, PageStore
from .paths import DEFAULT_DATA_DIR, DEFAULT_DB_PATH, DEFAULT_SEED_PATH
from .verdict_models import load_verdict_models

logger = logging.getLogger(__name__)

# cap saved pages per host
MAX_PAGES_PER_HOST = 60


def run_crawl() -> None:
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
    try:
        verdict_models = load_verdict_models()
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    with PageStore(DEFAULT_DB_PATH) as page_store, LinkStore(DEFAULT_DB_PATH) as link_store:
        try:
            crawl_hostname(
                config,
                page_store,
                link_store,
                page_critic=verdict_models.page,
                link_critic=verdict_models.link,
            )
        except Exception as exc:
            logger.error("Failed to crawl with error %s", exc)
            return


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)

    if args[:1] == ["report"]:
        report_main(args[1:])
        return

    parser = argparse.ArgumentParser(prog="crawl")
    parser.add_argument(
        "command",
        nargs="?",
        choices=["report"],
        help="run without a command to start the crawler",
    )
    parsed = parser.parse_args(args)
    if parsed.command == "report":
        report_main([])
        return

    run_crawl()


if __name__ == "__main__":
    main()
