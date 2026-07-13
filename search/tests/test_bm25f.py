"""Tests for field-weighted ranking (BM25F): title/URL matches count for more
than body matches, and title/URL terms become searchable."""

from pathlib import Path

from tuebingen_search.indexer import _build_search_index, _document_fields, _url_field_text
from tuebingen_search.models import Document, DocumentField
from tuebingen_search.scoring import _normalize_field_tf, compute_bm25f_idf


def make_document(name: str, terms: tuple[str, ...], *, url: str | None = None, title: str | None = None) -> Document:
    return Document(path=Path(name), url=url, length=len(terms), terms=terms, title=title)


def make_positions(term_freq_index):
    return {
        document: {term: list(range(count)) for term, count in term_frequency.items()}
        for document, term_frequency in term_freq_index.items()
    }


def test_url_field_text_keeps_path_drops_host():
    assert _url_field_text("https://www.trip.com/travel-guide/tubingen") == "/travel-guide/tubingen"
    assert _url_field_text("https://example.test/search?q=museum") == "/search?q=museum"
    assert _url_field_text("https://example.test") == ""
    assert _url_field_text(None) == ""


def test_document_fields_splits_body_title_url():
    document = make_document("a.html", ("apple",), url="https://x.test/food-guide", title="Fresh Apples")
    fields = _document_fields(document, {"apple": 1})

    assert fields[DocumentField.BODY] == {"apple": 1}
    assert fields[DocumentField.TITLE] == {"fresh": 1, "apples": 1}
    assert fields[DocumentField.URL] == {"food": 1, "guide": 1}


def test_normalize_field_tf_penalizes_long_fields():
    assert _normalize_field_tf(2, 10, 10) == 2
    assert _normalize_field_tf(2, 20, 10) < 2
    assert _normalize_field_tf(0, 10, 10) == 0


def test_title_match_outranks_body_only_match():
    # both documents contain "tuebingen" once; only the first has it in the title
    doc_title = make_document("title.html", ("tuebingen",), title="tuebingen")
    doc_body = make_document("body.html", ("tuebingen",), title=None)
    term_freq_index = {doc_title: {"tuebingen": 1}, doc_body: {"tuebingen": 1}}

    search_index = _build_search_index(term_freq_index, make_positions(term_freq_index))
    postings = {p.doc_index: p for p in search_index.inverted_index["tuebingen"]}

    # doc 0 (title match) must score strictly higher than doc 1 (body only)
    assert postings[0].score > postings[1].score


def test_url_only_term_becomes_searchable_without_positions():
    document = make_document("u.html", ("apple",), url="https://x.test/food-guide")
    term_freq_index = {document: {"apple": 1}}

    search_index = _build_search_index(term_freq_index, make_positions(term_freq_index))

    # "food" appears only in the URL, so it is searchable but has no body positions
    assert "food" in search_index.inverted_index
    food_posting = search_index.inverted_index["food"][0]
    assert food_posting.doc_index == 0
    assert food_posting.positions == []
    assert food_posting.score > 0


def test_bm25f_idf_counts_term_across_any_field():
    doc_one = make_document("one.html", ("apple",), title="pear")
    doc_two = make_document("two.html", ("apple",))
    field_frequencies = {
        doc_one: _document_fields(doc_one, {"apple": 1}),
        doc_two: _document_fields(doc_two, {"apple": 1}),
    }

    idf = compute_bm25f_idf(field_frequencies)

    # "apple" is in both docs, "pear" (title of doc one) in a single doc -> higher idf
    assert idf["pear"] > idf["apple"]
