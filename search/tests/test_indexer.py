# search/tests/test_indexer.py
import math
from pathlib import Path

import msgpack
import pytest

from tuebingen_search.indexer import (
    SNIPPET_MAX_TERMS,
    Document,
    build_search_index,
    compute_df,
    compute_idf,
    compute_tf,
    compute_tf_idf,
    index,
)


def make_document(name: str) -> Document:
    return Document(path=Path(name), length=0, text_snippet="")


def test_compute_tf_counts_term_occurrences():
    assert compute_tf(["a", "b", "a", "c", "a"]) == {"a": 3, "b": 1, "c": 1}


def test_compute_tf_empty():
    assert compute_tf([]) == {}


def test_compute_df_counts_documents_per_term():
    term_freq_index = {
        make_document("one.html"): {"apple": 3, "pear": 1},
        make_document("two.html"): {"apple": 1},
    }
    assert compute_df(term_freq_index) == {"apple": 2, "pear": 1}


def test_compute_idf_uses_smoothed_formula():
    term_freq_index = {
        make_document("one.html"): {"common": 1, "rare": 1},
        make_document("two.html"): {"common": 1},
    }
    idf = compute_idf(term_freq_index)

    assert idf["common"] == pytest.approx(math.log(3 / 3) + 1.0)
    assert idf["rare"] == pytest.approx(math.log(3 / 2) + 1.0)
    # rarer terms score higher
    assert idf["rare"] > idf["common"]


def test_compute_tf_idf_multiplies():
    assert compute_tf_idf(3, 1.5) == pytest.approx(4.5)


def test_build_search_index_preserves_document_order():
    doc_one = make_document("one.html")
    doc_two = make_document("two.html")
    search_index = build_search_index({doc_one: {"apple": 1}, doc_two: {"pear": 1}})

    assert search_index.documents == [doc_one, doc_two]


def test_build_search_index_postings_point_to_correct_documents():
    doc_one = make_document("one.html")
    doc_two = make_document("two.html")
    search_index = build_search_index(
        {doc_one: {"apple": 2, "pear": 1}, doc_two: {"apple": 1}}
    )

    apple_postings = search_index.inverted_index["apple"]
    assert [posting.doc_index for posting in apple_postings] == [0, 1]
    # doc one has the term twice, so its tf-idf score is double
    assert apple_postings[0].score == pytest.approx(2 * apple_postings[1].score)

    pear_postings = search_index.inverted_index["pear"]
    assert [posting.doc_index for posting in pear_postings] == [0]


def test_build_search_index_empty():
    search_index = build_search_index({})
    assert search_index.documents == []
    assert search_index.inverted_index == {}


def test_index_writes_msgpack_file(tmp_path):
    html_dir = tmp_path / "html"
    site_a = html_dir / "site_a"
    site_b = html_dir / "site_b"
    site_a.mkdir(parents=True)
    site_b.mkdir(parents=True)
    (site_a / "a.html").write_text(
        "<html><body><p>apple banana apple</p></body></html>", encoding="utf-8"
    )
    (site_b / "b.html").write_text(
        "<html><body><p>banana cherry</p></body></html>", encoding="utf-8"
    )
    (site_a / "skip.txt").write_text("not html", encoding="utf-8")
    index_path = tmp_path / "index.bin"

    index(str(html_dir), str(index_path))

    with index_path.open("rb") as index_file:
        data = msgpack.unpack(index_file, raw=False)

    paths = [entry[0] for entry in data["documents"]]
    assert paths == [str(site_a / "a.html"), str(site_b / "b.html")]
    assert set(data["inverted_index"]) == {"apple", "banana", "cherry"}

    # "banana" occurs in both documents, "cherry" only in the second
    banana_docs = [doc_index for doc_index, _ in data["inverted_index"]["banana"]]
    assert banana_docs == [0, 1]
    cherry_docs = [doc_index for doc_index, _ in data["inverted_index"]["cherry"]]
    assert cherry_docs == [1]


def test_index_stores_document_length(tmp_path):
    html_dir = tmp_path / "html"
    site_dir = html_dir / "site"
    site_dir.mkdir(parents=True)
    (site_dir / "a.html").write_text(
        "<html><body><p>one two three four</p></body></html>", encoding="utf-8"
    )
    index_path = tmp_path / "index.bin"

    index(str(html_dir), str(index_path))

    with index_path.open("rb") as index_file:
        data = msgpack.unpack(index_file, raw=False)

    _, length, _ = data["documents"][0]
    assert length == 4


def test_index_caps_snippet_length(tmp_path):
    html_dir = tmp_path / "html"
    site_dir = html_dir / "site"
    site_dir.mkdir(parents=True)
    words = " ".join(f"word{i}" for i in range(SNIPPET_MAX_TERMS * 3))
    (site_dir / "long.html").write_text(
        f"<html><body><p>{words}</p></body></html>", encoding="utf-8"
    )
    index_path = tmp_path / "index.bin"

    index(str(html_dir), str(index_path))

    with index_path.open("rb") as index_file:
        data = msgpack.unpack(index_file, raw=False)

    _, _, snippet = data["documents"][0]
    assert len(snippet.split()) == SNIPPET_MAX_TERMS
