import math
from collections import Counter

from .models import (
    AverageFieldLengths,
    Document,
    DocumentField,
    FieldLengths,
    FieldTermFrequencies,
    TermFrequency,
)

# Titles and URLs carry more intent than body text.
FIELD_WEIGHTS: dict[DocumentField, float] = {
    DocumentField.BODY: 1.0,
    DocumentField.TITLE: 5.0,
    DocumentField.URL: 3.0,
}
# Prevent long fields from winning solely through more terms.
FIELD_B = 0.75
# Prevent repeated terms from dominating relevance.
K1 = 1.2


def compute_tf(terms: list[str]) -> TermFrequency:
    return dict(Counter(terms))


def compute_bm25f_idf(
    field_frequencies: dict[Document, FieldTermFrequencies],
) -> dict[str, float]:
    n_docs = len(field_frequencies)
    document_frequency: Counter[str] = Counter()
    for fields in field_frequencies.values():
        terms_in_document: set[str] = set()
        for term_frequency in fields.values():
            terms_in_document.update(term_frequency)
        document_frequency.update(terms_in_document)

    return {
        term: math.log(1.0 + (n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
        for term, doc_freq in document_frequency.items()
    }


def compute_average_field_lengths(
    field_frequencies: dict[Document, FieldTermFrequencies],
) -> AverageFieldLengths:
    totals: Counter[DocumentField] = Counter()
    for fields in field_frequencies.values():
        for field, term_frequency in fields.items():
            totals[field] += sum(term_frequency.values())

    n_docs = len(field_frequencies) or 1
    return {field: total / n_docs for field, total in totals.items()}


def _normalize_field_tf(
    frequency: int,
    field_length: int,
    average_field_length: float,
) -> float:
    if frequency <= 0 or average_field_length <= 0:
        return 0.0

    length_norm = 1.0 - FIELD_B + FIELD_B * (field_length / average_field_length)
    return frequency / length_norm


def compute_bm25f_score(
    *,
    term_frequency_per_field: dict[DocumentField, int],
    idf_score: float,
    field_lengths: FieldLengths,
    average_field_lengths: AverageFieldLengths,
) -> float:
    weighted_term_frequency = sum(
        FIELD_WEIGHTS[field]
        * _normalize_field_tf(
            frequency,
            field_lengths[field],
            average_field_lengths[field],
        )
        for field, frequency in term_frequency_per_field.items()
    )

    if weighted_term_frequency <= 0:
        return 0.0

    return idf_score * (weighted_term_frequency / (K1 + weighted_term_frequency))
