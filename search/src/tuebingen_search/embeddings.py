from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from .html import extract_text_from_html
from .models import Document
from .storage import elapsed, load_index

logger = logging.getLogger(__name__)

# Paraphrase/STS model, not retrieval-trained.
MODEL_NAME = "sentence-transformers/paraphrase-MiniLM-L6-v2"
EMBEDDINGS_FORMAT_VERSION = 2
PASSAGE_CHARS = int(os.environ.get('PASSAGE_CHARS', '2000'))
PASSAGE_OVERLAP = int(os.environ.get('PASSAGE_OVERLAP', '200'))
MAX_PASSAGES_PER_DOC = int(os.environ.get('MAX_PASSAGES_PER_DOC', '20'))


@dataclass(frozen=True)
class PassageEmbeddings:
    """Passage vectors and row ranges for each document."""

    vectors: np.ndarray
    doc_slices: list[slice]

    @classmethod
    def from_doc_ids(
        cls,
        vectors: np.ndarray,
        doc_ids: np.ndarray,
        document_count: int,
    ) -> PassageEmbeddings:
        vectors = np.asarray(vectors, dtype=np.float32)
        doc_ids = np.asarray(doc_ids)
        if vectors.ndim != 2:
            raise ValueError('Embedding vectors must be a two-dimensional array.')
        if doc_ids.ndim != 1 or len(doc_ids) != len(vectors):
            raise ValueError('doc_ids must contain one document id per passage vector.')
        if not np.issubdtype(doc_ids.dtype, np.integer):
            raise ValueError('doc_ids must be integers.')
        if len(doc_ids) and (
            np.any(doc_ids < 0)
            or np.any(doc_ids >= document_count)
            or np.any(doc_ids[1:] < doc_ids[:-1])
        ):
            raise ValueError('doc_ids must be sorted valid document indices.')

        boundaries = np.searchsorted(doc_ids, np.arange(document_count + 1))
        doc_slices = [
            slice(int(boundaries[i]), int(boundaries[i + 1]))
            for i in range(document_count)
        ]
        return cls(vectors=vectors, doc_slices=doc_slices)

    @classmethod
    def from_document_vectors(cls, vectors: np.ndarray) -> PassageEmbeddings:
        """Adapt the legacy one-vector-per-document representation."""
        vectors = np.asarray(vectors, dtype=np.float32)
        return cls.from_doc_ids(vectors, np.arange(len(vectors)), len(vectors))

    def mean_document_vectors(self) -> np.ndarray:
        """Return one map-compatible vector per document."""
        means = np.zeros((len(self.doc_slices), self.vectors.shape[1]), dtype=np.float32)
        for doc_index, passage_slice in enumerate(self.doc_slices):
            passages = self.vectors[passage_slice]
            if len(passages):
                means[doc_index] = passages.mean(axis=0)
        return means


@lru_cache(maxsize=1)
def get_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> np.ndarray:
    vectors = get_model().encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 100,
    )
    return np.asarray(vectors, dtype=np.float32)


def split_passages(
    text: str,
    passage_chars: int = PASSAGE_CHARS,
    overlap: int = PASSAGE_OVERLAP,
    max_passages: int = MAX_PASSAGES_PER_DOC,
) -> list[str]:
    """Split text into capped overlapping character windows."""
    if passage_chars <= 0 or max_passages <= 0:
        raise ValueError('passage_chars and max_passages must be positive.')
    if overlap < 0 or overlap >= passage_chars:
        raise ValueError('overlap must be non-negative and smaller than passage_chars.')
    if not text:
        return []

    step = passage_chars - overlap
    passages: list[str] = []
    for start in range(0, len(text), step):
        passages.append(text[start : start + passage_chars])
        if len(passages) == max_passages or start + passage_chars >= len(text):
            break
    return passages


def build_embeddings(index_path: Path, out_path: Path) -> None:
    """Write vectors, passage-to-document doc_ids, paths, and format_version to NPZ."""
    start = time.perf_counter()
    index = load_index(index_path)

    logger.info('Extracting passages from %d documents...', len(index.documents))
    passages: list[str] = []
    doc_ids: list[int] = []
    for doc_index, document in enumerate(index.documents):
        document_passages = split_passages(extract_text_from_html(document.path))
        passages.extend(document_passages)
        doc_ids.extend([doc_index] * len(document_passages))

    logger.info('Encoding %d passages with %s...', len(passages), MODEL_NAME)
    if passages:
        vectors = embed_texts(passages)
    else:
        vectors = np.empty((0, 0), dtype=np.float32)

    # Paths guard alignment; doc_ids maps every passage row to its document.
    paths = np.array([str(document.path) for document in index.documents])
    np.savez(
        out_path,
        vectors=np.asarray(vectors, dtype=np.float32),
        doc_ids=np.asarray(doc_ids, dtype=np.int64),
        paths=paths,
        format_version=np.array(EMBEDDINGS_FORMAT_VERSION, dtype=np.int16),
    )
    logger.info('Saved %d passage embeddings to %s in %s', len(vectors), out_path, elapsed(start))


def load_embeddings(path: Path, documents: list[Document]) -> PassageEmbeddings | None:
    if not Path(path).exists():
        return None

    with np.load(path, allow_pickle=False) as data:
        if list(data['paths']) != [str(document.path) for document in documents]:
            logger.warning(
                'Embeddings at %s do not match the current index, falling back to BM25 only. '
                'Run `uv run embed` to rebuild them.',
                path,
            )
            return None

        try:
            vectors = data['vectors']
            if 'doc_ids' in data.files:
                doc_ids = data['doc_ids']
            else:
                # Older files stored exactly one row per document.
                if len(vectors) != len(documents):
                    raise ValueError('legacy files need one vector per document')
                doc_ids = np.arange(len(vectors))
            return PassageEmbeddings.from_doc_ids(vectors, doc_ids, len(documents))
        except ValueError as error:
            logger.warning(
                'Embeddings at %s are invalid (%s), falling back to BM25 only. '
                'Run `uv run embed` to rebuild them.',
                path,
                error,
            )
            return None
