from __future__ import annotations

import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from .embeddings import embed_texts, get_model, load_embeddings
from .search import SearchResult, load_index, search_index
from .paths import DEFAULT_INDEX_PATH, DEFAULT_EMBEDDINGS_PATH


logger = logging.getLogger(__name__)

# load index once at startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    index_path = Path(os.environ.get("INDEX_PATH", str(DEFAULT_INDEX_PATH)))
    if not index_path.exists():
        raise RuntimeError(f"Search index does not exist: {index_path}.")

    logger.info("Loading index from %s", index_path)
    app.state.index = load_index(index_path)

    embeddings_path = Path(os.environ.get("EMBEDDINGS_PATH", str(DEFAULT_EMBEDDINGS_PATH)))
    app.state.doc_embeddings = load_embeddings(embeddings_path, app.state.index.documents)
    if app.state.doc_embeddings is None:
        logger.warning("No embeddings at %s, serving lexical ranking only.", embeddings_path)
    else:
        logger.info("Loading embedding model...")
        get_model()
    yield


app = FastAPI(title="Tübingen Search", lifespan=lifespan)


@app.get("/search", response_model=list[SearchResult])
def search_api(
    q: str = Query(min_length=1),
    top_n: int = Query(10, ge=1, le=100),
    context_size: int = Query(20, ge=1, le=100),
):
    return search_index(app.state.index, q, top_n, context_size, app.state.doc_embeddings)


@app.get("/map")
def map_api(x: str = Query(min_length=1), y: str = Query(min_length=1)):
    embeddings = app.state.doc_embeddings
    if embeddings is None:
        raise HTTPException(status_code=503, detail="Embeddings not available, run `uv run embed`.")

    document_embeddings = embeddings.mean_document_vectors()
    if document_embeddings.shape[1] == 0:
        raise HTTPException(status_code=503, detail='Embeddings contain no passages.')

    x_axis, y_axis = embed_texts([x, y])
    xs = document_embeddings @ x_axis
    ys = document_embeddings @ y_axis
    return [
        {"url": document.url, "title": document.title, "x": float(xs[i]), "y": float(ys[i])}
        for i, document in enumerate(app.state.index.documents)
        if document.url
    ]


@app.get("/health")
def health():
    return {"status": "ok", "documents": len(app.state.index.documents)}
