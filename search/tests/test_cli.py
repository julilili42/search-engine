# search/tests/test_cli.py
import pytest

from tuebingen_search.cli import build_parser


def test_index_command_defaults():
    args = build_parser().parse_args(["index"])
    assert args.command == "index"
    assert args.dir == "../data/tuepedia/html"
    assert args.output == "index.bin"


def test_index_command_custom_arguments():
    args = build_parser().parse_args(["index", "-d", "/tmp/html", "-o", "/tmp/out.bin"])
    assert args.dir == "/tmp/html"
    assert args.output == "/tmp/out.bin"


def test_search_command_requires_query():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["search"])


def test_search_command_defaults():
    args = build_parser().parse_args(["search", "-q", "tübingen"])
    assert args.command == "search"
    assert args.index == "index.bin"
    assert args.query == "tübingen"
    assert args.top_n == 10


def test_command_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
