from __future__ import annotations

import logging
import math
import os
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import Body, FastAPI, HTTPException, Query, Response
from .batch import format_batch, parse_batch, search_loaded_batch
from .embeddings import embed_texts, load_embeddings
from .search import ALPHA, BETA, SearchResult, load_index, search_index
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
    yield


app = FastAPI(title="Tübingen Search", lifespan=lifespan)


@app.get("/search", response_model=list[SearchResult])
def search_api(
    q: str = Query(min_length=1),
    top_n: int = Query(10, ge=1, le=100),
    context_size: int = Query(20, ge=1, le=100),
    cat_x: str | None = Query(None, min_length=1),
    cat_y: str | None = Query(None, min_length=1),
    proximity: bool = Query(False),
    semantic: bool = Query(True),
    alpha: float = Query(ALPHA, ge=0, le=1),
    beta: float = Query(BETA, ge=0, le=1),
):
    if not math.isclose(alpha + beta, 1.0):
        raise HTTPException(422, "alpha and beta must sum to 1")
    category_axes = None
    if app.state.doc_embeddings is not None and (cat_x or cat_y):
        labels = [label for label in (cat_x, cat_y) if label]
        embeddings = iter(embed_texts(labels))
        category_axes = tuple(next(embeddings) if label else None for label in (cat_x, cat_y))
    return search_index(
        app.state.index,
        q,
        top_n,
        context_size,
        app.state.doc_embeddings,
        category_axes,
        use_proximity=proximity,
        use_semantic=semantic,
        alpha=alpha,
        beta=beta,
    )


@app.get("/health")
def health():
    return {"status": "ok", "documents": len(app.state.index.documents)}


@app.post("/batch")
def batch_api(
    data: str = Body(media_type="text/plain"),
    top_n: int = Query(100, ge=1, le=100),
):
    try:
        batch = parse_batch(data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    results = search_loaded_batch(
        app.state.index, app.state.doc_embeddings, batch, top_n
    )
    return Response(
        format_batch(results),
        media_type="text/tab-separated-values",
        headers={"Content-Disposition": 'attachment; filename="results.tsv"'},
    )
