from __future__ import annotations

import heapq
import logging
import time

from collections.abc import Sequence
from pathlib import Path

import numpy as np

from .embeddings import PassageEmbeddings, embed_texts, load_embeddings
from .models import (
    DocumentScores,
    DocumentTermPositions,
    ScoredDocument,
    SearchIndex,
    SearchResult,
    TermPosition,
)
from .paths import DEFAULT_EMBEDDINGS_PATH
from .tokenizer import tokenize
from .storage import load_index, elapsed


logger = logging.getLogger(__name__)

RERANK_CANDIDATES = 100
SEMANTIC_CANDIDATES = 100
# BERT supplements BM25 but should not dominate it.
ALPHA = 0.7
TITLE_SIMILARITY_WEIGHT = 0.20
BEST_PASSAGE_WEIGHT = 0.65
TOP_PASSAGES_MEAN_WEIGHT = 0.15


def search(index_path: Path, query: str, top_n: int, context_size: int = 20) -> list[SearchResult]:
    index = load_index(index_path)
    doc_embeddings = load_embeddings(DEFAULT_EMBEDDINGS_PATH, index.documents)
    category_axes = (
        embed_texts([CATEGORY_X_LABEL, CATEGORY_Y_LABEL])
        if doc_embeddings is not None
        else None
    )
    return search_index(index, query, top_n, context_size, doc_embeddings, category_axes)

# fixed category axes the result "constellation" is placed on: how strongly a
# result matches each label becomes its x/y coordinate in the universe view
CATEGORY_X_LABEL = "university, research and administration"
CATEGORY_Y_LABEL = "tourism, culture and everyday life"


def search_index(
    index: SearchIndex,
    query: str,
    top_n: int,
    context_size: int = 20,
    doc_embeddings: PassageEmbeddings | np.ndarray | None = None,
    category_axes: np.ndarray | None = None,
) -> list[SearchResult]:
    start = time.perf_counter()
    query_terms = set(tokenize(query))

    if not query_terms:
        logger.warning("No searchable query terms in query.")
        return []

    logger.info("Searching for %r ...", " ".join(query_terms))

    scores: DocumentScores = {}
    term_positions: DocumentTermPositions = {}

    for term in query_terms:
        for posting in index.inverted_index.get(term, []):
            scores[posting.doc_index] = scores.get(posting.doc_index, 0.0) + posting.score
            term_positions.setdefault(posting.doc_index, {})[term] = posting.positions

    for doc_index, doc_term_positions in term_positions.items():
        scores[doc_index] += _proximity_bonus(doc_term_positions)

    embedding_scores: dict[int, float] = {}
    document_embeddings: np.ndarray | None = None
    if doc_embeddings is not None:
        passage_embeddings = _as_passage_embeddings(doc_embeddings)
        if (
            len(passage_embeddings.doc_slices) != len(index.documents)
            or passage_embeddings.vectors.shape[1] == 0
        ):
            logger.warning('Embeddings are unusable for this index; using lexical ranking only.')
            ranked_results = heapq.nlargest(top_n, scores.items(), key=lambda item: item[1])
        else:
            document_embeddings = passage_embeddings.mean_document_vectors()
            query_embedding = embed_texts([query])[0]
            semantic_scores = _semantic_scores(passage_embeddings, query_embedding)
            lexical = heapq.nlargest(
                max(top_n, RERANK_CANDIDATES),
                scores.items(),
                key=lambda item: item[1],
            )
            semantic = heapq.nlargest(
                max(top_n, SEMANTIC_CANDIDATES),
                (
                    (doc_index, float(semantic_scores[doc_index]))
                    for doc_index, passage_slice in enumerate(passage_embeddings.doc_slices)
                    if passage_slice.start != passage_slice.stop
                ),
                key=lambda item: item[1],
            )
            candidate_ids = {doc_index for doc_index, _ in lexical + semantic}
            candidates = [
                (doc_index, scores.get(doc_index, 0.0))
                for doc_index in sorted(candidate_ids)
            ]
            reranked = _rerank(
                candidates,
                passage_embeddings,
                query_embedding,
                semantic_scores=semantic_scores,
            )[:top_n]
            ranked_results = [(doc_index, score) for doc_index, score, _ in reranked]
            embedding_scores = {doc_index: cosine for doc_index, _, cosine in reranked}
    else:
        ranked_results = heapq.nlargest(top_n, scores.items(), key=lambda item: item[1])

    # place each result on fixed category axes (how strongly it matches
    # CATEGORY_X_LABEL / CATEGORY_Y_LABEL) so the constellation reflects
    # meaningful topics instead of an arbitrary rank spiral
    embedding_coords: dict[int, tuple[float, float]] = {}
    if document_embeddings is not None and category_axes is not None and ranked_results:
        doc_indices = [doc_index for doc_index, _ in ranked_results]
        coords = project_onto_categories(
            document_embeddings[doc_indices], category_axes[0], category_axes[1]
        )
        embedding_coords = dict(zip(doc_indices, coords))

    search_results: list[SearchResult] = []

    for rank, (doc_index, score) in enumerate(ranked_results, start=1):
        document = index.documents[doc_index]
        path, url, terms = document.path, document.url, document.terms

        snippet = _generate_snippet(terms, term_positions.get(doc_index, {}), context_size)
        xy = embedding_coords.get(doc_index)

        search_results.append(
            SearchResult(
                rank=rank,
                score=score,
                path=path,
                url=url,
                snippet=snippet,
                title=document.title,
                embedding_score=embedding_scores.get(doc_index),
                embedding_x=xy[0] if xy else None,
                embedding_y=xy[1] if xy else None,
            )
        )

    logger.info("Search computation took %s", elapsed(start))
    return search_results


def _as_passage_embeddings(
    embeddings: PassageEmbeddings | np.ndarray,
) -> PassageEmbeddings:
    if isinstance(embeddings, PassageEmbeddings):
        return embeddings
    return PassageEmbeddings._from_document_vectors(embeddings)


def _best_passage_scores(
    embeddings: PassageEmbeddings | np.ndarray,
    query_embedding: np.ndarray,
) -> np.ndarray:
    # A document is as relevant as its best matching passage
    passage_embeddings = _as_passage_embeddings(embeddings)
    scores = np.zeros(len(passage_embeddings.doc_slices), dtype=np.float32)
    passage_scores = passage_embeddings.vectors @ query_embedding
    for doc_index, passage_slice in enumerate(passage_embeddings.doc_slices):
        document_scores = passage_scores[passage_slice]
        if len(document_scores):
            scores[doc_index] = document_scores.max()
    return scores


def _semantic_scores(
    passage_embeddings: PassageEmbeddings,
    query_embedding: np.ndarray,
) -> np.ndarray:
    if passage_embeddings.title_vectors is None:
        return _best_passage_scores(passage_embeddings, query_embedding)

    passage_scores = passage_embeddings.vectors @ query_embedding
    title_scores = passage_embeddings.title_vectors @ query_embedding
    scores = np.zeros(len(passage_embeddings.doc_slices), dtype=np.float32)
    for doc_index, passage_slice in enumerate(passage_embeddings.doc_slices):
        document_scores = passage_scores[passage_slice]
        if len(document_scores):
            top = np.sort(document_scores)[-3:]
            scores[doc_index] = (
                TITLE_SIMILARITY_WEIGHT * title_scores[doc_index]
                + BEST_PASSAGE_WEIGHT * top[-1]
                + TOP_PASSAGES_MEAN_WEIGHT * top.mean()
            )
    return scores


def _rerank(
    candidates: list[ScoredDocument],
    doc_embeddings: PassageEmbeddings | np.ndarray,
    query_embedding: np.ndarray,
    alpha: float = ALPHA,
    semantic_scores: np.ndarray | None = None,
) -> list[tuple[int, float, float]]:
    if not candidates:
        return []
    doc_indices = [doc_index for doc_index, _ in candidates]
    lexical = np.array([score for _, score in candidates])

    spread = lexical.max() - lexical.min()
    lexical_norm = (lexical - lexical.min()) / spread if spread > 0 else np.zeros_like(lexical)
    if semantic_scores is None:
        semantic_scores = _semantic_scores(
            _as_passage_embeddings(doc_embeddings), query_embedding
        )
    cosine = semantic_scores[doc_indices]

    blended = alpha * lexical_norm + (1 - alpha) * cosine
    order = np.argsort(-blended)
    return [(doc_indices[i], float(blended[i]), float(cosine[i])) for i in order]


def project_onto_categories(
    vectors: np.ndarray, x_axis: np.ndarray, y_axis: np.ndarray
) -> list[tuple[float, float]]:
    """Place each vector by how strongly it matches two named category embeddings."""
    if len(vectors) == 0:
        return []

    def center_and_scale(values: np.ndarray) -> np.ndarray:
        centered = values - values.mean()
        std = values.std() or 1.0
        # tanh instead of max-abs: a single outlier saturates gracefully instead of
        # linearly compressing every near-duplicate result onto the same point
        return np.tanh(centered / (2 * std))

    xs = center_and_scale(vectors @ x_axis)
    ys = center_and_scale(vectors @ y_axis)
    return list(zip((float(x) for x in xs), (float(y) for y in ys)))


def _best_window(term_positions: TermPosition) -> tuple[int, int] | None:
    if len(term_positions) < 2:
        return None

    events = sorted(
        (position, term)
        for term in term_positions
        for position in term_positions[term]
    )
    counts: dict[str, int] = {}
    left = 0
    best: tuple[int, int] | None = None

    for right_position, right_term in events:
        counts[right_term] = counts.get(right_term, 0) + 1

        while len(counts) == len(term_positions):
            left_position, left_term = events[left]
            if best is None or right_position - left_position < best[1] - best[0]:
                best = (left_position, right_position)

            counts[left_term] -= 1
            if counts[left_term] == 0:
                del counts[left_term]
            left += 1

    return best


def _proximity_bonus(term_positions: TermPosition, boost: float = 0.25) -> float:
    window = _best_window(term_positions)
    if window is None:
        return 0.0

    extra_gap = (window[1] - window[0] + 1) - len(term_positions)
    return boost / (1 + extra_gap)


def _generate_snippet(
    terms: Sequence[str],
    term_positions: TermPosition,
    context_size: int,
) -> str:
    # Prefer a repeated match in the article body over title/navigation text.
    later_positions = {
        term: [position for position in positions if position >= 30]
        for term, positions in term_positions.items()
    }
    snippet_positions = (
        later_positions
        if later_positions and all(later_positions.values())
        else term_positions
    )
    window = _best_window(snippet_positions)
    if window is not None:
        position = (window[0] + window[1]) // 2
    else:
        positions = [p for ps in snippet_positions.values() for p in ps]
        if not positions:
            return " ".join(terms[: 2 * context_size + 1])
        position = min(positions)

    start = max(0, position - context_size)
    end = min(len(terms), position + context_size + 1)

    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(terms) else ""

    return prefix + " ".join(terms[start:end]) + suffix
