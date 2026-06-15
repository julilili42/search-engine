from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

from .html import extract_text_from_html, is_html_file
from .tokenizer import tokenize
from .models import Document, TermFrequency, SearchIndex, Posting
from .scoring import compute_idf, compute_tf_idf, compute_tf
from .storage import save_index
from .load_pages import PageLoad

logger = logging.getLogger(__name__)

SNIPPET_MAX_TERMS = 40

def build_search_index(term_freq_index: dict[Document, TermFrequency]) -> SearchIndex:
    idf = compute_idf(term_freq_index)
    documents: list[Document] = []
    # retrieval of all urls which contain a word, fast lookup for given word
    inverted_index: defaultdict[str, list[Posting]] = defaultdict(list)

    for document, term_frequency in term_freq_index.items():
        doc_index = len(documents)
        documents.append(document)
        add_document_to_index(inverted_index, doc_index, term_frequency, idf)

    return SearchIndex(documents, dict(inverted_index))


def add_document_to_index(
    inverted_index: defaultdict[str, list[Posting]],
    doc_index: int,
    term_frequency: TermFrequency,
    idf: dict[str, float],
) -> None:
    for term, frequency in term_frequency.items():
        score = compute_tf_idf(frequency, idf.get(term, 0.0))
        inverted_index[term].append(Posting(doc_index=doc_index, score=score))


def index(index_path: Path, pages_db: PageLoad) -> None:
    term_frequency_index: dict[Document, TermFrequency] = {}
    
    logger.info("Iterating over pages...")
    records = pages_db.iter_html_pages()
    previous_host = ""
    for record in records:
        file_path = record.path

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
        text = extract_text_from_html(file_path)
        terms = tokenize(text)

        document = Document(
            path=file_path,
            url=record.url,
            length=len(terms),
            text_snippet=" ".join(terms[:SNIPPET_MAX_TERMS]),
        )
        term_frequency_index[document] = compute_tf(terms)

    logger.info("Computing inverted index...")
    search_index = build_search_index(term_frequency_index)

    logger.info("Saving %s", index_path)
    save_index(index_path, search_index)    