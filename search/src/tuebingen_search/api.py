from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query

from .search import SearchResult, load_index, search_index

logger = logging.getLogger(__name__)

# load index once at startup
@asynccontextmanager
async def lifespan(app: FastAPI):
    index_path = os.environ.get("INDEX_PATH", "index.bin")
    logger.info("Loading index from %s", index_path)
    app.state.index = load_index(index_path)
    yield


app = FastAPI(title="Tübingen Search", lifespan=lifespan)


@app.get("/search", response_model=list[SearchResult])
def search_api(
    q: str = Query(min_length=1),
    top_n: int = Query(10, ge=1, le=100),
):
    return search_index(app.state.index, q, top_n)


@app.get("/health")
def health():
    return {"status": "ok", "documents": len(app.state.index.documents)}
