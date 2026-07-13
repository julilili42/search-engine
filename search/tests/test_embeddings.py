from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from tuebingen_search.embeddings import BATCH_SIZE, MODEL_NAME, _mean_pool, embed_texts, load_embeddings
from tuebingen_search.models import Document


def make_document(path: str) -> Document:
    return Document(path=Path(path), url=None, length=0, terms=())


def test_load_embeddings_missing_file_returns_none(tmp_path):
    assert load_embeddings(tmp_path / "missing.npz", []) is None


def test_load_embeddings_rejects_stale_file(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    np.savez(out_path, vectors=np.zeros((1, 4), dtype=np.float32), paths=np.array(["/old/a.html"]))

    assert load_embeddings(out_path, [make_document("/new/b.html")]) is None


def test_load_embeddings_rejects_different_model(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    np.savez(
        out_path,
        vectors=np.zeros((1, 4), dtype=np.float32),
        paths=np.array(["/a.html"]),
        model="old-model",
    )

    assert load_embeddings(out_path, [make_document("/a.html")]) is None


def test_load_embeddings_returns_matching_vectors(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    vectors = np.ones((2, 4), dtype=np.float32)
    np.savez(
        out_path,
        vectors=vectors,
        paths=np.array(["/a.html", "/b.html"]),
        model=MODEL_NAME,
    )

    loaded = load_embeddings(out_path, [make_document("/a.html"), make_document("/b.html")])
    assert np.array_equal(loaded, vectors)


def test_mean_pool_ignores_padding():
    token_embeddings = torch.tensor([[[1.0, 3.0], [3.0, 5.0], [99.0, 99.0]]])
    attention_mask = torch.tensor([[1, 1, 0]])

    assert torch.equal(_mean_pool(token_embeddings, attention_mask), torch.tensor([[2.0, 4.0]]))


def test_embed_texts_mean_pools_and_normalizes(monkeypatch):
    class Tokenizer:
        def __call__(self, texts, **_kwargs):
            return {"attention_mask": torch.tensor([[1, 1, 0]] * len(texts))}

    class Model:
        def __call__(self, **_inputs):
            batch_size = len(_inputs["attention_mask"])
            return SimpleNamespace(
                last_hidden_state=torch.tensor([[[3.0, 4.0], [0.0, 0.0], [99.0, 99.0]]] * batch_size)
            )

    monkeypatch.setattr("tuebingen_search.embeddings.get_model", lambda: (Tokenizer(), Model()))

    assert np.allclose(embed_texts(["example"] * (BATCH_SIZE + 1)), [[0.6, 0.8]] * (BATCH_SIZE + 1))
