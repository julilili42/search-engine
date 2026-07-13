from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path

import numpy as np

from .html import extract_text_from_html
from .models import Document
from .storage import load_index, elapsed

logger = logging.getLogger(__name__)

# Paraphrase/STS model, not retrieval-trained.
MODEL_NAME = "sentence-transformers/paraphrase-MiniLM-L6-v2"
# the model's 128-token window sees roughly this much anyway
MAX_TEXT_CHARS = 2000


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


def build_embeddings(index_path: Path, out_path: Path) -> None:
    start = time.perf_counter()
    index = load_index(index_path)

    logger.info("Extracting text from %d documents...", len(index.documents))
    texts = [extract_text_from_html(document.path)[:MAX_TEXT_CHARS] for document in index.documents]

    logger.info("Encoding with %s...", MODEL_NAME)
    vectors = embed_texts(texts)

    # stored paths detect a stale file after an index rebuild instead of silently misaligning rows
    paths = np.array([str(document.path) for document in index.documents])
    np.savez(out_path, vectors=vectors, paths=paths)
    logger.info("Saved %d embeddings to %s in %s", len(vectors), out_path, elapsed(start))


def load_embeddings(path: Path, documents: list[Document]) -> np.ndarray | None:
    if not Path(path).exists():
        return None

    data = np.load(path, allow_pickle=False)
    if list(data["paths"]) != [str(document.path) for document in documents]:
        logger.warning(
            "Embeddings at %s do not match the current index, falling back to BM25 only. "
            "Run `uv run embed` to rebuild them.",
            path,
        )
        return None

    return data["vectors"]
