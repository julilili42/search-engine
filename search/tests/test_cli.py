# search/tests/test_cli.py
from pathlib import Path

import pytest

from tuebingen_search.cli import build_index_parser, build_search_parser


def test_index_defaults():
    args = build_index_parser().parse_args([])
    assert Path(args.output).name == "index.bin"
    assert Path(args.output).parent.name == "data"
    assert Path(args.db).name == "pages.sqlite"


def test_index_custom_arguments():
    args = build_index_parser().parse_args(["--db", "/tmp/pages.sqlite", "-o", "/tmp/out.bin"])
    assert args.db == Path("/tmp/pages.sqlite")
    assert args.output == Path("/tmp/out.bin")


def test_search_requires_query():
    with pytest.raises(SystemExit):
        build_search_parser().parse_args([])


def test_search_defaults():
    args = build_search_parser().parse_args(["-q", "tübingen"])
    assert Path(args.index).name == "index.bin"
    assert Path(args.index).parent.name == "data"
    assert args.query == "tübingen"
    assert args.top_n == 10
