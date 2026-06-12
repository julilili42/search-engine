from __future__ import annotations
import argparse

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
