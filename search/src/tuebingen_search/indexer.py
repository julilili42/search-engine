from __future__ import annotations

import logging
import time

from collections import defaultdict
from pathlib import Path

from .html import extract_text_from_html, is_html_file
from .tokenizer import tokenize
from .models import Document, TermFrequency, TermPosition, SearchIndex, Posting
from .scoring import (
    compute_bm25_idf,
    compute_bm25_score,
    compute_average_document_length,
    compute_tf,
)
from .storage import save_index, elapsed
from .load_pages import PageLoad

logger = logging.getLogger(__name__)

def build_search_index(term_freq_index: dict[Document, TermFrequency], term_positions: dict[Document, TermPosition]) -> SearchIndex:
    idf = compute_bm25_idf(term_freq_index)
    average_document_length = compute_average_document_length(term_freq_index)

    documents: list[Document] = []
    # retrieval of all urls which contain a word, fast lookup for given word
    inverted_index: defaultdict[str, list[Posting]] = defaultdict(list)

    for doc_index, (document, term_frequency) in enumerate(term_freq_index.items()):
        documents.append(document)

        term_position = term_positions[document]
        add_document_to_index(
            inverted_index,
            doc_index,
            document,
            term_frequency,
            term_position,
            idf,
            average_document_length,
        )

    return SearchIndex(documents, dict(inverted_index))


def add_document_to_index(
    inverted_index: defaultdict[str, list[Posting]],
    doc_index: int,
    document: Document,
    term_frequency: TermFrequency,
    term_position: dict[str, list[int]],
    idf: dict[str, float],
    average_document_length: float,
) -> None:
    for term, frequency in term_frequency.items():
        score = compute_bm25_score(
            term_frequency=frequency,
            idf_score=idf.get(term, 0.0),
            document_length=document.length,
            average_document_length=average_document_length,
        )
        inverted_index[term].append(Posting(doc_index=doc_index, score=score, positions=term_position[term]))

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
            terms=tuple(terms)
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
