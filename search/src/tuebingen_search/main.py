from pathlib import Path
import logging
from collections.abc import Sequence

from .embeddings import build_embeddings
from .indexer import index
from .search import search
from .cli import build_index_parser, build_search_parser, build_embed_parser
from .load_pages import PageLoad


def index_main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_index_parser().parse_args(argv)
    output_path = Path(args.output)
    if not args.db.exists():
        raise SystemExit(
            f"Crawl database not found: {args.db}. Run `uv run crawl` first "
            "or pass an existing database with `uv run index --db PATH`."
        )
    pages_db = PageLoad(args.db)

    index(output_path, pages_db)


def embed_main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_embed_parser().parse_args(argv)
    if not args.index.exists():
        raise SystemExit(f"Index not found: {args.index}. Run `uv run index` first.")
    build_embeddings(args.index, args.output)


def search_main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_search_parser().parse_args(argv)
    for result in search(args.index, args.query, args.top_n, args.context_size):
        print(
            f"\n{result.rank:>2}. score:   {result.score:>8.3f}\n"
            f"    path:    {result.path}\n"
            f"    url:    {result.url}\n"
            f"    snippet: {result.snippet}"
        )
