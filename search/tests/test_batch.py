import pytest

from tuebingen_search.batch import (
    export_batch,
    import_batch,
    run_batch,
    search_batch,
)
from tuebingen_search.indexer import index
from tuebingen_search.models import Document, SearchResult
from helpers import make_page_load

PAGES = {
    "apple.html": "<html><body><p>apple apple apple banana</p></body></html>",
    "banana.html": "<html><body><p>banana banana cherry</p></body></html>",
    "cherry.html": "<html><body><p>cherry orange</p></body></html>",
}


@pytest.fixture
def index_path(tmp_path):
    site_dir = tmp_path / "html" / "site"
    site_dir.mkdir(parents=True)
    for name, content in PAGES.items():
        (site_dir / name).write_text(content, encoding="utf-8")

    path = tmp_path / "index.bin"
    pages = {site_dir / name: "text/html; charset=utf-8" for name in PAGES}
    index(path, make_page_load(tmp_path / "pages.sqlite", pages))
    return path


def write_queries(path, lines):
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_import_batch_parses_tab_separated_queries(tmp_path):
    query_file = write_queries(
        tmp_path / "queries.tsv",
        ["1\ttübingen attractions", "2\tfood and drinks"],
    )

    assert import_batch(query_file) == {
        1: "tübingen attractions",
        2: "food and drinks",
    }


def test_import_batch_skips_blank_lines_and_trims(tmp_path):
    query_file = write_queries(
        tmp_path / "queries.tsv",
        ["1\t  spaced query  ", "", "2\tsecond"],
    )

    assert import_batch(query_file) == {1: "spaced query", 2: "second"}


def test_import_batch_rejects_non_integer_query_id(tmp_path):
    query_file = write_queries(tmp_path / "queries.tsv", ["one\tapple"])

    with pytest.raises(ValueError):
        import_batch(query_file)


def test_import_batch_rejects_wrong_column_count(tmp_path):
    query_file = write_queries(tmp_path / "queries.tsv", ["1\tapple\textra"])

    with pytest.raises(ValueError):
        import_batch(query_file)


def test_search_batch_returns_results_per_query(index_path):
    results = search_batch(index_path, {1: "banana", 2: "cherry"}, top_n=10)

    assert set(results) == {1, 2}
    assert all(isinstance(r, SearchResult) for r in results[1])
    # banana.html (twice) ranks above apple.html (once)
    assert str(results[1][0].path).endswith("banana.html")


def test_search_batch_respects_top_n(index_path):
    results = search_batch(index_path, {1: "banana cherry"}, top_n=1)

    assert len(results[1]) == 1


def test_export_batch_writes_run_file_format(tmp_path):
    results = {
        1: [
            SearchResult(rank=1, score=0.725, path=tmp_path, url="https://a.test/1", snippet=""),
            SearchResult(rank=2, score=0.671, path=tmp_path, url="https://a.test/2", snippet=""),
        ]
    }
    out = tmp_path / "results.tsv"

    export_batch(out, results)

    rows = [line.split("\t") for line in out.read_text(encoding="utf-8").splitlines()]
    assert rows == [
        ["1", "1", "https://a.test/1", "0.7250"],
        ["1", "2", "https://a.test/2", "0.6710"],
    ]


def test_export_batch_skips_url_less_results_and_keeps_ranks_contiguous(tmp_path):
    results = {
        1: [
            SearchResult(rank=1, score=0.9, path=tmp_path, url=None, snippet=""),
            SearchResult(rank=2, score=0.8, path=tmp_path, url="https://a.test/2", snippet=""),
            SearchResult(rank=3, score=0.7, path=tmp_path, url="https://a.test/3", snippet=""),
        ]
    }
    out = tmp_path / "results.tsv"

    export_batch(out, results)

    rows = [line.split("\t") for line in out.read_text(encoding="utf-8").splitlines()]
    # url-less result dropped, ranks renumbered 1, 2 without gaps
    assert [row[:3] for row in rows] == [
        ["1", "1", "https://a.test/2"],
        ["1", "2", "https://a.test/3"],
    ]


def test_run_batch_end_to_end(index_path, tmp_path):
    query_file = write_queries(
        tmp_path / "queries.tsv", ["1\tbanana", "2\tcherry"]
    )
    out = tmp_path / "results.tsv"

    run_batch(index_path, query_file, out, top_n=100)

    lines = out.read_text(encoding="utf-8").splitlines()
    query_ids = {line.split("\t")[0] for line in lines}
    assert query_ids == {"1", "2"}
    # every line has exactly four tab-separated fields
    assert all(len(line.split("\t")) == 4 for line in lines)
