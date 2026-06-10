"""Index construction."""

from __future__ import annotations

import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import msgpack

from .html import extract_text_from_html, is_html_file
from .tokenizer import tokenize

logger = logging.getLogger(__name__)

TermFrequency = dict[str, int]

SNIPPET_MAX_TERMS = 40


@dataclass(frozen=True)
class Posting:
    doc_index: int
    score: float


@dataclass(frozen=True)
class Document:
    path: Path
    length: int
    text_snippet: str


@dataclass(frozen=True)
class SearchIndex:
    documents: list[Document]
    inverted_index: dict[str, list[Posting]]


def compute_tf(terms: list[str]) -> TermFrequency:
    return dict(Counter(terms))


def compute_df(index: dict[Document, TermFrequency]) -> TermFrequency:
    df: Counter[str] = Counter()
    for tf in index.values():
        df.update(tf.keys())
    return dict(df)


def compute_idf(index: dict[Document, TermFrequency]) -> dict[str, float]:
    n = len(index)
    return {
        term: math.log((1.0 + n) / (1.0 + freq)) + 1.0
        for term, freq in compute_df(index).items()
    }


def compute_tf_idf(frequency: int, idf_score: float) -> float:
    return frequency * idf_score


def build_search_index(term_freq_index: dict[Document, TermFrequency]) -> SearchIndex:
    idf = compute_idf(term_freq_index)
    documents: list[Document] = []
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


def index(dir_path: str, index_path: str) -> None:
    directory = Path(dir_path)
    term_frequency_index: dict[Document, TermFrequency] = {}
    
    
    folder_paths = sorted(folder_path for folder_path in directory.iterdir() if folder_path.is_dir())
    number_of_folders = len(folder_paths) 


    for i, folder_path in enumerate(folder_paths):
        logger.info("Indexing folder %d/%d: %s", i + 1, number_of_folders, folder_path)
        
        file_paths = sorted(
            file_path
            for file_path in folder_path.rglob("*")
            if file_path.is_file()
        )

        for file_path in file_paths:
            if not is_html_file(file_path):
                logger.warning("Skipped non-html file: %s", file_path)
                continue

            logger.debug("Indexing %s", file_path)
            text = extract_text_from_html(file_path)
            terms = tokenize(text)
            document = Document(
                path=file_path,
                length=len(terms),
                text_snippet=" ".join(terms[:SNIPPET_MAX_TERMS]),
            )
            term_frequency_index[document] = compute_tf(terms)

    for document, tf in term_frequency_index.items():
        logger.debug("%s has %d unique tokens", document.path, len(tf))

    logger.info("Computing inverted index...")
    search_index = build_search_index(term_frequency_index)

    logger.info("Saving %s...", index_path)
    with Path(index_path).open("wb") as index_file:
        msgpack.pack(_to_msgpack(search_index), index_file, use_bin_type=True)


def _to_msgpack(search_index: SearchIndex) -> dict[str, object]:
    return {
        "documents": [
            [str(document.path), document.length, document.text_snippet]
            for document in search_index.documents
        ],
        "inverted_index": {
            term: [[posting.doc_index, posting.score] for posting in postings]
            for term, postings in search_index.inverted_index.items()
        },
    }
