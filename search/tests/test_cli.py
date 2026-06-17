# search/tests/test_cli.py
from pathlib import Path

import pytest

from tuebingen_search.cli import build_parser


def test_index_command_defaults():
    args = build_parser().parse_args(["index"])
    assert args.command == "index"
    assert Path(args.output).name == "index.bin"
    assert Path(args.db).name == "pages.sqlite"


def test_index_command_custom_arguments():
    args = build_parser().parse_args(
        ["index", "--db", "/tmp/pages.sqlite", "-o", "/tmp/out.bin"]
    )
    assert args.db == Path("/tmp/pages.sqlite")
    assert args.output == Path("/tmp/out.bin")


def test_search_command_requires_query():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["search"])


def test_search_command_defaults():
    args = build_parser().parse_args(["search", "-q", "tübingen"])
    assert args.command == "search"
    assert Path(args.index).name == "index.bin"
    assert args.query == "tübingen"
    assert args.top_n == 10


def test_command_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
