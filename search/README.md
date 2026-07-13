# Search

Builds a BM25 inverted index over the crawled pages and serves retrieval through
a CLI and a FastAPI endpoint.

## Setup

```bash
uv sync
```

(Workspace member — run from the repo root.)

## Usage

Build the index from the crawled pages (`data/pages.sqlite` → `data/index.bin`):

```bash
uv run index
```

Interactive single query:

```bash
uv run search -q "tübingen attractions" -t 5
```

HTTP API (`/search`, `/health`) used by the client:

```bash
uv run uvicorn tuebingen_search.api:app
```
