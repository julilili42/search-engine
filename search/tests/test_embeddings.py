from pathlib import Path

import numpy as np

from tuebingen_search.embeddings import embed_texts, load_embeddings, split_passages
from tuebingen_search.models import Document


def make_document(path: str) -> Document:
    return Document(path=Path(path), url=None, length=0, terms=())


def test_load_embeddings_missing_file_returns_none(tmp_path):
    assert load_embeddings(tmp_path / "missing.npz", []) is None


def test_load_embeddings_rejects_stale_file(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    np.savez(out_path, vectors=np.zeros((1, 4), dtype=np.float32), paths=np.array(["/old/a.html"]))

    assert load_embeddings(out_path, [make_document("/new/b.html")]) is None


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
    )

    loaded = load_embeddings(out_path, documents)
    # Passage files return row slices instead of the legacy document-vector array.
    assert loaded is not None
    assert np.array_equal(loaded.vectors, vectors)
    assert np.array_equal(loaded.vectors[loaded.doc_slices[0]], vectors[:2])
    assert np.array_equal(loaded.vectors[loaded.doc_slices[1]], vectors[2:])
    assert np.allclose(loaded.mean_document_vectors(), [vectors[:2].mean(axis=0), vectors[2]])


def test_load_embeddings_adapts_legacy_document_vectors(tmp_path):
    out_path = tmp_path / "embeddings.npz"
    vectors = np.eye(2, dtype=np.float32)
    documents = [make_document("/a.html"), make_document("/b.html")]
    np.savez(out_path, vectors=vectors, paths=np.array([str(document.path) for document in documents]))

    loaded = load_embeddings(out_path, documents)

    assert loaded is not None
    assert loaded.doc_slices == [slice(0, 1), slice(1, 2)]
    assert np.array_equal(loaded.vectors, vectors)


def test_split_passages_overlaps_and_caps_windows():
    passages = split_passages('abcdefghij', passage_chars=4, overlap=1, max_passages=3)

    assert passages == ['abcd', 'defg', 'ghij']


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
