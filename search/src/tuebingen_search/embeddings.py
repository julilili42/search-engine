from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from .html import extract_text_from_html
from .models import Document
from .storage import elapsed, load_index

logger = logging.getLogger(__name__)

MODEL_NAME = "google-bert/bert-base-uncased"
MAX_TOKENS = 512
BATCH_SIZE = 32

PASSAGE_CHARS = 2000
PASSAGE_OVERLAP = 200
MAX_PASSAGES_PER_DOC = 20


@dataclass(frozen=True)
# Documents have variable passage counts; slices preserve their vector ranges.
class PassageEmbeddings:
    vectors: np.ndarray
    doc_slices: list[slice]

    @classmethod
    def _from_doc_ids(
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
    def _from_document_vectors(cls, vectors: np.ndarray) -> PassageEmbeddings:
        vectors = np.asarray(vectors, dtype=np.float32)
        return cls._from_doc_ids(vectors, np.arange(len(vectors)), len(vectors))

    def mean_document_vectors(self) -> np.ndarray:
        # The map needs one vector per document.
        means = np.zeros((len(self.doc_slices), self.vectors.shape[1]), dtype=np.float32)
        for doc_index, passage_slice in enumerate(self.doc_slices):
            passages = self.vectors[passage_slice]
            if len(passages):
                means[doc_index] = passages.mean(axis=0)
        return means


def build_embeddings(index_path: Path, out_path: Path) -> None:
    start = time.perf_counter()
    index = load_index(index_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info('Extracting passages from %d documents...', len(index.documents))
    passages: list[str] = []
    doc_ids: list[int] = []
    for doc_index, document in enumerate(index.documents):
        document_passages = _split_passages(extract_text_from_html(document.path))
        passages.extend(document_passages)
        doc_ids.extend([doc_index] * len(document_passages))

    logger.info('Encoding %d passages with %s...', len(passages), MODEL_NAME)
    if passages:
        vectors = embed_texts(passages)
    else:
        vectors = np.empty((0, 0), dtype=np.float32)

    # Paths reject stale indexes; doc_ids restore each passage's document.
    paths = np.array([str(document.path) for document in index.documents])
    np.savez(
        out_path,
        vectors=np.asarray(vectors, dtype=np.float32),
        doc_ids=np.asarray(doc_ids, dtype=np.int64),
        paths=paths,
        model=MODEL_NAME,
    )
    logger.info('Saved %d passage embeddings to %s in %s', len(vectors), out_path, elapsed(start))


def load_embeddings(path: Path, documents: list[Document]) -> PassageEmbeddings | None:
    if not Path(path).exists():
        return None

    with np.load(path, allow_pickle=False) as data:
        if (
            'model' not in data.files
            or data['model'].item() != MODEL_NAME
            or list(data['paths']) != [str(document.path) for document in documents]
        ):
            logger.warning(
                'Embeddings at %s do not match the current index or model, falling back to '
                'BM25 only. Run `uv run embed` to rebuild them.',
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
            return PassageEmbeddings._from_doc_ids(vectors, doc_ids, len(documents))
        except ValueError as error:
            logger.warning(
                'Embeddings at %s are invalid (%s), falling back to BM25 only. '
                'Run `uv run embed` to rebuild them.',
                path,
                error,
            )
            return None


def embed_texts(texts: list[str]) -> np.ndarray:
    tokenizer, model = _get_model()
    vectors = []
    for start in range(0, len(texts), BATCH_SIZE):
        inputs = tokenizer(
            texts[start : start + BATCH_SIZE],
            padding=True,
            truncation=True,
            max_length=MAX_TOKENS,
            return_tensors="pt",
        )
        with torch.inference_mode():
            pooled = _mean_pool(model(**inputs).last_hidden_state, inputs["attention_mask"])
        vectors.append(torch.nn.functional.normalize(pooled, dim=1))
    return torch.cat(vectors).numpy().astype(np.float32)


def _split_passages(
    text: str,
    passage_chars: int = PASSAGE_CHARS,
    overlap: int = PASSAGE_OVERLAP,
    max_passages: int = MAX_PASSAGES_PER_DOC,
) -> list[str]:
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


@lru_cache(maxsize=1)
def _get_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)
    model.eval()
    return tokenizer, model


def _mean_pool(token_embeddings: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    weights = attention_mask.unsqueeze(-1).to(token_embeddings.dtype)
    return (token_embeddings * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1)
