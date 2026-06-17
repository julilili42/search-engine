from __future__ import annotations
import argparse
from pathlib import Path
from .paths import DEFAULT_DB_PATH, DEFAULT_INDEX_PATH, DEFAULT_BATCH_PATH, DEFAULT_RESULT_PATH

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tuebingen-search",
        description="Small search engine for TUEpedia HTML files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    index_parser.add_argument("-o", "--output", type=Path, default=DEFAULT_INDEX_PATH)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("-i", "--index", type=Path, default=DEFAULT_INDEX_PATH)
    search_parser.add_argument("-q", "--query", required=True)
    search_parser.add_argument("-t", "--top-n", type=int, default=10)
    search_parser.add_argument("-c", "--context-size", type=int, default=20)

    batch_parser = subparsers.add_parser("batch")
    batch_parser.add_argument("-i", "--index", type=Path, default=DEFAULT_INDEX_PATH)
    batch_parser.add_argument("-b", "--batch", type=Path, default=DEFAULT_BATCH_PATH)
    batch_parser.add_argument("-o", "--output", type=Path, default=DEFAULT_RESULT_PATH)
    batch_parser.add_argument("-t", "--top-n", type=int, default=100)

    return parser
