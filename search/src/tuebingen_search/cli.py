"""Command line interface."""

from __future__ import annotations

import argparse
import logging

from .indexer import index
from .search import search


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuebingen-search",
        description="Small search engine for TUEpedia HTML files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("-d", "--dir", default="../data2")
    index_parser.add_argument("-o", "--output", default="index.bin")

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("-i", "--index", default="index.bin")
    search_parser.add_argument("-q", "--query", required=True)
    search_parser.add_argument("-t", "--top-n", type=int, default=10)

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = build_parser().parse_args()

    if args.command == "index":
        index(args.dir, args.output)
    elif args.command == "search":
        for result in search(args.index, args.query, args.top_n):
            print(
                f"\n{result.rank:>2}. score:   {result.score:>8.3f}\n"
                f"    path:    {result.path}\n"
                f"    snippet: {result.snippet}"
            )


if __name__ == "__main__":
    main()
