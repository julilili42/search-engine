from pathlib import Path
import logging
from .indexer import index
from .search import search
from .cli import build_parser
from .load_pages import PageLoad

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args()
    if args.command == "index":
        output_path = Path(args.output)
        pages_db = PageLoad(args.db)

        index(output_path, pages_db)
    elif args.command == "search":
        for result in search(args.index, args.query, args.top_n):
            print(
                f"\n{result.rank:>2}. score:   {result.score:>8.3f}\n"
                f"    path:    {result.path}\n"
                f"    url:    {result.url}\n"
                f"    snippet: {result.snippet}"
            )
