from __future__ import annotations

import logging
import os
import time

from collections import defaultdict
from pathlib import Path

from .html import extract_text_from_html, is_html_file
from .tokenizer import tokenize
from .models import Document, TermFrequency, TermPosition, SearchIndex, Posting
from .scoring import (
    DEFAULT_FIELD_B,
    DEFAULT_FIELD_WEIGHTS,
    FieldTermFrequencies,
    compute_average_field_lengths,
    compute_bm25f_idf,
    compute_bm25f_score,
    compute_tf,
)
from .storage import save_index, elapsed
from .load_pages import PageLoad

logger = logging.getLogger(__name__)


def url_field_text(url: str | None) -> str:
    """Slug words of a URL: drop the scheme and host, keep the path/query.

    The host ("www", "trip", "com") is mostly noise, while the path often
    carries meaningful terms (".../tourist-attractions/tubingen-44519").
    """
    if not url:
        return ""
    without_scheme = url.split("://", 1)[-1]
    slash = without_scheme.find("/")
    return without_scheme[slash:] if slash != -1 else ""


def _field_setting(env_prefix: str, defaults: dict[str, float]) -> dict[str, float]:
    """Field weights / b-values, overridable via env for benchmark tuning."""
    setting = dict(defaults)
    for field in defaults:
        value = os.environ.get(f"{env_prefix}_{field.upper()}")
        if value is not None:
            try:
                setting[field] = float(value)
            except ValueError:
                logger.warning("Ignoring invalid %s_%s=%r", env_prefix, field.upper(), value)
    return setting

def document_fields(document: Document, body_frequency: TermFrequency) -> FieldTermFrequencies:
    """Term frequencies per field (body/title/url) for one document.

    The body frequencies are already computed during indexing; title and URL
    are tokenised here from the fields the Document already carries, so the
    stored index schema stays unchanged.
    """
    return {
        "body": body_frequency,
        "title": compute_tf(tokenize(document.title or "")),
        "url": compute_tf(tokenize(url_field_text(document.url))),
    }


def build_search_index(term_freq_index: dict[Document, TermFrequency], term_positions: dict[Document, TermPosition]) -> SearchIndex:
    weights = _field_setting("BM25F_W", DEFAULT_FIELD_WEIGHTS)
    field_b = _field_setting("BM25F_B", DEFAULT_FIELD_B)

    field_frequencies: dict[Document, FieldTermFrequencies] = {
        document: document_fields(document, body_frequency)
        for document, body_frequency in term_freq_index.items()
    }

    idf = compute_bm25f_idf(field_frequencies)
    average_field_lengths = compute_average_field_lengths(field_frequencies)

    documents: list[Document] = []
    # retrieval of all urls which contain a word, fast lookup for given word
    inverted_index: defaultdict[str, list[Posting]] = defaultdict(list)

    for doc_index, (document, fields) in enumerate(field_frequencies.items()):
        documents.append(document)
        add_document_to_index(
            inverted_index,
            doc_index,
            fields,
            term_positions[document],
            idf,
            average_field_lengths,
            weights,
            field_b,
        )

    return SearchIndex(documents, dict(inverted_index))


def add_document_to_index(
    inverted_index: defaultdict[str, list[Posting]],
    doc_index: int,
    fields: FieldTermFrequencies,
    term_position: dict[str, list[int]],
    idf: dict[str, float],
    average_field_lengths: dict[str, float],
    weights: dict[str, float],
    field_b: dict[str, float],
) -> None:
    field_lengths = {field: sum(tf.values()) for field, tf in fields.items()}

    # a term is searchable if it appears in any field (body, title or url)
    all_terms: set[str] = set()
    for term_frequency in fields.values():
        all_terms.update(term_frequency)

    for term in all_terms:
        score = compute_bm25f_score(
            term_frequency_per_field={field: fields[field].get(term, 0) for field in fields},
            idf_score=idf.get(term, 0.0),
            field_lengths=field_lengths,
            average_field_lengths=average_field_lengths,
            weights=weights,
            field_b=field_b,
        )
        # positions come from the body only; title/url-only terms have none,
        # and snippet generation already handles missing positions
        inverted_index[term].append(
            Posting(doc_index=doc_index, score=score, positions=term_position.get(term, []))
        )

def index(index_path: Path, pages_db: PageLoad) -> None:
    start = time.perf_counter()
    extraction_time = 0.0

    term_frequency_index: dict[Document, TermFrequency] = {}
    term_positions: dict[Document, TermPosition] = {}

    logger.info("Iterating over pages...")
    records = pages_db.iter_html_pages()
    previous_host = ""
    for record in records:
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
            logger.info(f"Indexing {record.host}")
            previous_host = record.host

        logger.debug("Indexing %s", file_path)

        start_extraction = time.perf_counter()
        text = extract_text_from_html(file_path)
        extraction_time += (time.perf_counter() - start_extraction)

        terms = tokenize(text)

        document = Document(
            path=file_path,
            url=record.url,
            length=len(terms),
            terms=tuple(terms),
            title=record.title or None,
        )

        # collecting indices at which terms appear, s.t. we can generate a query based snippet in the search
        positions: TermPosition = defaultdict(list)
        for position, term in enumerate(terms):
            positions[term].append(position)

        term_positions[document] = positions
        term_frequency_index[document] = compute_tf(terms)

    logger.info("Computing inverted index...")
    search_index = build_search_index(term_frequency_index, term_positions)

    logger.info("Saving %s", index_path)
    save_index(index_path, search_index)
    logger.info(f"Index computation took {elapsed(start)}")
    logger.info(f"Extraction time took {extraction_time:.6f} s")
