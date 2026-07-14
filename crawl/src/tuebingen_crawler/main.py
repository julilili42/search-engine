from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from .frontier import MAX_SAVED_PAGES_PER_HOST
from .report import report_main
from .scheduler import crawl_hostname
from .storage import load_seed_toml
from .models import Config
from .save_pages import LinkStore, PageStore
from .paths import DEFAULT_DATA_DIR, DEFAULT_SEED_PATH
from .verdict_models import load_verdict_models

def run_crawl(
    seed_path: Path = DEFAULT_SEED_PATH, data_dir: Path = DEFAULT_DATA_DIR
) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    html_dir = data_dir / "html"
    db_path = data_dir / "pages.sqlite"
    html_dir.mkdir(parents=True, exist_ok=True)

    sites = load_seed_toml(seed_path)
    config = Config(
        sites=sites,
        save_dir=html_dir,
        state_dir=data_dir,
        max_pages_per_host=MAX_SAVED_PAGES_PER_HOST,
    )
    try:
        verdict_models = load_verdict_models()
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    with PageStore(db_path) as page_store, LinkStore(db_path) as link_store:
        crawl_hostname(
            config,
            page_store,
            link_store,
            page_critic=verdict_models.page,
            link_critic=verdict_models.link,
        )


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
    parser.add_argument("--seeds", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parsed = parser.parse_args(args)
    if parsed.command == "report":
        report_main([])
        return

    run_crawl(parsed.seeds, parsed.data_dir)


if __name__ == "__main__":
    main()
