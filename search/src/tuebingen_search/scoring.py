import math
from collections import Counter
from .models import Document, TermFrequency

def compute_tf(terms: list[str]) -> TermFrequency:
    return dict(Counter(terms))

# tf-idf
def compute_df(index: dict[Document, TermFrequency]) -> TermFrequency:
    df: Counter[str] = Counter()
    for tf in index.values():
        df.update(tf.keys())
    return dict(df)

def compute_idf(index: dict[Document, TermFrequency]) -> dict[str, float]:
    N = len(index)
    return {
        term: math.log((1.0 + N) / (1.0 + doc_freq)) + 1.0
        for term, doc_freq in compute_df(index).items()
    }

def compute_tf_idf(term_frequency: int, idf_score: float) -> float:
    score = term_frequency * idf_score
    return score

# bm25
def compute_bm25_idf(index: dict[Document, TermFrequency]) -> dict[str, float]:
    n_docs = len(index)
    return {
        term: math.log(1.0 + (n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
        for term, doc_freq in compute_df(index).items()
    }

def compute_average_document_length(index: dict[Document, TermFrequency]) -> float:
    if not index:
        return 0.0

    return sum(document.length for document in index.keys()) / len(index)

def compute_bm25_score(
    *,
    term_frequency: int,
    idf_score: float,
    document_length: int,
    average_document_length: float,
    k1: float = 1.2,
    b: float = 0.75,
) -> float:
    if term_frequency <= 0 or average_document_length <= 0:
        return 0.0

    length_norm = 1.0 - b + b * (document_length / average_document_length)

    return idf_score * (
        (term_frequency * (k1 + 1.0))
        / (term_frequency + k1 * length_norm)
    )


# bm25f (field-weighted bm25)
#
# Title and URL matches should count for more than a match buried in the body.
# Postings store a *precomputed* score, so this weighting must happen at index
# time. We use the standard BM25F formulation: each field's term frequency is
# length-normalised on its own, scaled by a field weight, summed across fields,
# and only then run through a single saturation curve.

# field -> {term: count} for one document
FieldTermFrequencies = dict[str, TermFrequency]

# Tuned on benchmark/retrieval (15 queries, 523 qrels): title/url weighting and
# b=0.75 lifted lexical nDCG@10 from 0.108 (body only) to 0.164 and MRR@10 from
# 0.233 to 0.399. Gains plateau beyond these values, so they stay moderate to
# avoid overfitting the small query set. Override per field via BM25F_W_* / BM25F_B_*.
DEFAULT_FIELD_WEIGHTS: dict[str, float] = {"body": 1.0, "title": 5.0, "url": 3.0}
DEFAULT_FIELD_B: dict[str, float] = {"body": 0.75, "title": 0.75, "url": 0.75}


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
) -> dict[str, float]:
    totals: Counter[str] = Counter()
    for fields in field_frequencies.values():
        for field, term_frequency in fields.items():
            totals[field] += sum(term_frequency.values())

    n_docs = len(field_frequencies) or 1
    return {field: total / n_docs for field, total in totals.items()}


def compute_bm25f_score(
    *,
    term_frequency_per_field: dict[str, int],
    idf_score: float,
    field_lengths: dict[str, int],
    average_field_lengths: dict[str, float],
    weights: dict[str, float],
    field_b: dict[str, float],
    k1: float = 1.2,
) -> float:
    weighted_term_frequency = 0.0
    for field, frequency in term_frequency_per_field.items():
        if frequency <= 0:
            continue

        average_length = average_field_lengths.get(field, 0.0)
        if average_length <= 0:
            continue

        b = field_b.get(field, 0.75)
        length_norm = 1.0 - b + b * (field_lengths.get(field, 0) / average_length)
        weighted_term_frequency += weights.get(field, 0.0) * (frequency / length_norm)

    if weighted_term_frequency <= 0:
        return 0.0

    return idf_score * (weighted_term_frequency / (k1 + weighted_term_frequency))

