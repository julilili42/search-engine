from pathlib import Path

import numpy as np

from tuebingen_search.embeddings import embed_texts, load_embeddings
from tuebingen_search.models import Document


def make_document(path: str) -> Document:
    return Document(path=Path(path), url=None, length=0, terms=())


def test_load_embeddings_missing_file_returns_none(tmp_path):
    assert load_embeddings(tmp_path / "missing.npz", []) is None


def test_load_embeddings_rejects_stale_file(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    np.savez(out_path, vectors=np.zeros((1, 4), dtype=np.float32), paths=np.array(["/old/a.html"]))

    assert load_embeddings(out_path, [make_document("/new/b.html")]) is None


def test_load_embeddings_returns_matching_vectors(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    vectors = np.ones((2, 4), dtype=np.float32)
    np.savez(out_path, vectors=vectors, paths=np.array(["/a.html", "/b.html"]))

    loaded = load_embeddings(out_path, [make_document("/a.html"), make_document("/b.html")])
    assert np.array_equal(loaded, vectors)


def test_embed_texts_semantic_similarity():
    vectors = embed_texts(
        [
            "Where can I eat good food in Tübingen?",
            "The best restaurants in the old town",
            "Hiking trails through the forest",
        ]
    )

    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-3)

    query, restaurants, hiking = vectors
    assert query @ restaurants > query @ hiking
