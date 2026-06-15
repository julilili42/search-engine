from __future__ import annotations
import argparse
from pathlib import Path

def build_parser() -> argparse.ArgumentParser:

    current_dir = Path(__file__).resolve().parent
    
    project_root = current_dir.parent.parent.parent
    db_path = project_root / "data" / "pages.sqlite"
    output_path = project_root / "index.bin"

    parser = argparse.ArgumentParser(
        prog="tuebingen-search",
        description="Small search engine for TUEpedia HTML files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--db", type=Path, default=db_path)
    index_parser.add_argument("-o", "--output", default=output_path)

    search_parser = subparsers.add_parser("search")
    search_parser.add_argument("-i", "--index", default=output_path)
    search_parser.add_argument("-q", "--query", required=True)
    search_parser.add_argument("-t", "--top-n", type=int, default=10)

    return parser
