from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

from tuebingen_search.embeddings import (
    BATCH_SIZE,
    MODEL_NAME,
    _mean_pool,
    embed_texts,
    load_embeddings,
    _split_passages,
)
from tuebingen_search.models import Document


def make_document(path: str) -> Document:
    return Document(path=Path(path), url=None, length=0, terms=())


def test_load_embeddings_missing_file_returns_none(tmp_path):
    assert load_embeddings(tmp_path / "missing.npz", []) is None


def test_load_embeddings_rejects_stale_file(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    np.savez(
        out_path,
        vectors=np.zeros((1, 4), dtype=np.float32),
        paths=np.array(["/old/a.html"]),
        model=MODEL_NAME,
    )

    assert load_embeddings(out_path, [make_document("/new/b.html")]) is None


def test_load_embeddings_rejects_different_model(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    document = make_document("/a.html")
    np.savez(
        out_path,
        vectors=np.zeros((1, 4), dtype=np.float32),
        paths=np.array([str(document.path)]),
        model="old-model",
    )

    assert load_embeddings(out_path, [document]) is None


def test_load_embeddings_returns_matching_passages(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    vectors = np.arange(12, dtype=np.float32).reshape(3, 4)
    documents = [make_document("/a.html"), make_document("/b.html")]
    np.savez(
        out_path,
        vectors=vectors,
        doc_ids=np.array([0, 0, 1]),
        # store the documents' own path strings so the check round-trips on any OS
        paths=np.array([str(document.path) for document in documents]),
        model=MODEL_NAME,
    )

    loaded = load_embeddings(out_path, documents)
    # Passage files return row slices instead of the legacy document-vector array.
    assert loaded is not None
    assert np.array_equal(loaded.vectors, vectors)
    assert np.array_equal(loaded.vectors[loaded.doc_slices[0]], vectors[:2])
    assert np.array_equal(loaded.vectors[loaded.doc_slices[1]], vectors[2:])
    assert np.allclose(loaded.mean_document_vectors(), [vectors[:2].mean(axis=0), vectors[2]])


def test_load_embeddings_returns_title_vectors(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    documents = [make_document("/a.html"), make_document("/b.html")]
    title_vectors = np.eye(2, dtype=np.float32)
    np.savez(
        out_path,
        vectors=np.eye(2, dtype=np.float32),
        doc_ids=np.array([0, 1]),
        title_vectors=title_vectors,
        paths=np.array([str(document.path) for document in documents]),
        model=MODEL_NAME,
    )

    loaded = load_embeddings(out_path, documents)

    assert loaded is not None
    assert np.array_equal(loaded.title_vectors, title_vectors)


def test_load_embeddings_adapts_legacy_document_vectors(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    vectors = np.eye(2, dtype=np.float32)
    documents = [make_document("/a.html"), make_document("/b.html")]
    np.savez(
        out_path,
        vectors=vectors,
        paths=np.array([str(document.path) for document in documents]),
        model=MODEL_NAME,
    )

    loaded = load_embeddings(out_path, documents)

    assert loaded is not None
    assert loaded.doc_slices == [slice(0, 1), slice(1, 2)]
    assert np.array_equal(loaded.vectors, vectors)


def test_split_passages_overlaps_and_caps_windows():
    passages = _split_passages('abcdefghij', passage_chars=4, overlap=1, max_passages=3)

    assert passages == ['abcd', 'defg', 'ghij']


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

    monkeypatch.setattr("tuebingen_search.embeddings._get_model", lambda: (Tokenizer(), Model()))

    assert np.allclose(embed_texts(["example"] * (BATCH_SIZE + 1)), [[0.6, 0.8]] * (BATCH_SIZE + 1))
