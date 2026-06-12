import math
from collections import Counter
from .models import Document, TermFrequency

def compute_tf(terms: list[str]) -> TermFrequency:
    return dict(Counter(terms))


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

