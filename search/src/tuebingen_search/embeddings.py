from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

from .html import extract_text_from_html
from .models import Document
from .storage import load_index, elapsed

logger = logging.getLogger(__name__)

MODEL_NAME = "google-bert/bert-base-uncased"
MAX_TEXT_CHARS = 2000
MAX_TOKENS = 128
BATCH_SIZE = 32


@lru_cache(maxsize=1)
def get_model():
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)
    model.eval()
    return tokenizer, model


def _mean_pool(token_embeddings: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    weights = attention_mask.unsqueeze(-1).to(token_embeddings.dtype)
    return (token_embeddings * weights).sum(dim=1) / weights.sum(dim=1).clamp_min(1)


def embed_texts(texts: list[str]) -> np.ndarray:
    tokenizer, model = get_model()
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


def build_embeddings(index_path: Path, out_path: Path) -> None:
    start = time.perf_counter()
    index = load_index(index_path)

    logger.info("Extracting text from %d documents...", len(index.documents))
    texts = [extract_text_from_html(document.path)[:MAX_TEXT_CHARS] for document in index.documents]

    logger.info("Encoding with %s...", MODEL_NAME)
    vectors = embed_texts(texts)

    # stored paths detect a stale file after an index rebuild instead of silently misaligning rows
    paths = np.array([str(document.path) for document in index.documents])
    np.savez(out_path, vectors=vectors, paths=paths, model=MODEL_NAME)
    logger.info("Saved %d embeddings to %s in %s", len(vectors), out_path, elapsed(start))


def load_embeddings(path: Path, documents: list[Document]) -> np.ndarray | None:
    if not Path(path).exists():
        return None

    data = np.load(path, allow_pickle=False)
    if (
        "model" not in data
        or data["model"].item() != MODEL_NAME
        or list(data["paths"]) != [str(document.path) for document in documents]
    ):
        logger.warning(
            "Embeddings at %s do not match the current index or model, falling back to BM25 only. "
            "Run `uv run embed` to rebuild them.",
            path,
        )
        return None

    return data["vectors"]
