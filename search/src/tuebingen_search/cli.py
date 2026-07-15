from __future__ import annotations
import argparse
from pathlib import Path
from .paths import (
    DEFAULT_DB_PATH,
    DEFAULT_INDEX_PATH,
    DEFAULT_EMBEDDINGS_PATH,
    DEFAULT_BATCH_PATH,
    DEFAULT_RESULT_PATH,
)


def build_index_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="index",
        description="Build the Tuebingen search index",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_INDEX_PATH)
    return parser


def build_search_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="search",
        description="Search the Tuebingen index",
    )
    parser.add_argument("-i", "--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("-q", "--query", required=True)
    parser.add_argument("-t", "--top-n", type=int, default=10)
    parser.add_argument("-c", "--context-size", type=int, default=20)
    return parser


def build_embed_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="embed",
        description="Build passage embeddings for the Tuebingen index",
    )
    parser.add_argument("-i", "--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_EMBEDDINGS_PATH)
    return parser


def build_batch_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="batch",
        description="Run batch search queries",
    )
    parser.add_argument("-i", "--index", type=Path, default=DEFAULT_INDEX_PATH)
    parser.add_argument("-b", "--batch", type=Path, default=DEFAULT_BATCH_PATH)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_RESULT_PATH)
    parser.add_argument("-t", "--top-n", type=int, default=100)
    return parser
