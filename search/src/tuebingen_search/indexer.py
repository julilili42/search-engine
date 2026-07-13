from __future__ import annotations

import logging
import time

from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from .html import extract_text_from_html, is_html_file
from .tokenizer import tokenize
from .models import (
    AverageFieldLengths,
    Document,
    DocumentField,
    FieldLengths,
    FieldTermFrequencies,
    TermFrequency,
    TermPosition,
    SearchIndex,
    Posting,
)
from .scoring import (
    compute_average_field_lengths,
    compute_bm25f_idf,
    compute_bm25f_score,
    compute_tf,
)
from .storage import save_index, elapsed
from .load_pages import PageLoad

logger = logging.getLogger(__name__)


def index(index_path: Path, pages_db: PageLoad) -> None:
    start = time.perf_counter()
    extraction_time = 0.0

    term_frequency_index: dict[Document, TermFrequency] = {}
    term_positions: dict[Document, TermPosition] = {}

    logger.info("Iterating over pages...")
    previous_host = ""
    for record in pages_db.iter_html_pages():
        file_path = record.path
        if file_path is None:
            logger.warning("Skipped page without file path: %s", record.url)
            continue

        if not file_path.exists():
            logger.warning("Skipped missing file: %s", file_path)
            continue

        if not is_html_file(file_path):
            logger.warning("Skipped non-html file: %s", file_path)
            continue

        if record.host != previous_host:
            logger.info("Indexing %s", record.host)
            previous_host = record.host

        logger.debug("Indexing %s", file_path)
        extraction_started = time.perf_counter()
        terms = tokenize(extract_text_from_html(file_path))
        extraction_time += time.perf_counter() - extraction_started

        document = Document(
            path=file_path,
            url=record.url,
            length=len(terms),
            terms=tuple(terms),
            title=record.title or None,
        )
        positions: TermPosition = defaultdict(list)
        for position, term in enumerate(terms):
            positions[term].append(position)

        term_positions[document] = positions
        term_frequency_index[document] = compute_tf(terms)

    logger.info("Computing inverted index...")
    search_index = _build_search_index(term_frequency_index, term_positions)
    logger.info("Saving %s", index_path)
    save_index(index_path, search_index)
    logger.info("Index computation took %s", elapsed(start))
    logger.info("Extraction time took %.6f s", extraction_time)


# Hosts are mostly noise.
def _url_field_text(url: str | None) -> str:
    if not url:
        return ""
    parsed = urlsplit(url)
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def _document_fields(document: Document, body_frequency: TermFrequency) -> FieldTermFrequencies:
    return {
        DocumentField.BODY: body_frequency,
        DocumentField.TITLE: compute_tf(tokenize(document.title or "")),
        DocumentField.URL: compute_tf(tokenize(_url_field_text(document.url))),
    }


def _build_search_index(term_freq_index: dict[Document, TermFrequency], term_positions: dict[Document, TermPosition]) -> SearchIndex:
    field_frequencies: dict[Document, FieldTermFrequencies] = {
        document: _document_fields(document, body_frequency)
        for document, body_frequency in term_freq_index.items()
    }

    idf = compute_bm25f_idf(field_frequencies)
    average_field_lengths = compute_average_field_lengths(field_frequencies)

    documents: list[Document] = []
    inverted_index: defaultdict[str, list[Posting]] = defaultdict(list)

    for doc_index, (document, fields) in enumerate(field_frequencies.items()):
        documents.append(document)
        _add_document_to_index(
            inverted_index,
            doc_index,
            fields,
            term_positions[document],
            idf,
            average_field_lengths,
        )

    return SearchIndex(documents, dict(inverted_index))


def _add_document_to_index(
    inverted_index: defaultdict[str, list[Posting]],
    doc_index: int,
    fields: FieldTermFrequencies,
    term_positions: TermPosition,
    idf: dict[str, float],
    average_field_lengths: AverageFieldLengths,
) -> None:
    field_lengths: FieldLengths = {field: sum(tf.values()) for field, tf in fields.items()}

    # Keep title/URL-only matches searchable.
    all_terms: set[str] = set()
    for term_frequency in fields.values():
        all_terms.update(term_frequency)

    for term in all_terms:
        score = compute_bm25f_score(
            term_frequency_per_field={field: fields[field].get(term, 0) for field in fields},
            idf_score=idf.get(term, 0.0),
            field_lengths=field_lengths,
            average_field_lengths=average_field_lengths,
        )
        # Snippets use body positions only.
        inverted_index[term].append(
            Posting(doc_index=doc_index, score=score, positions=term_positions.get(term, []))
        )
