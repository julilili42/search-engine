# Tübingen Search Engine

> A custom search engine with link crawling and an indexing pipeline and client frontend.

## Components

This repo is a uv workspace with separate components, each with its own README:

- [`crawl/`](crawl/README.md) — link crawler that fetches and stores pages
- [`search/`](search/README.md) — BM25 index, CLI, and FastAPI search API
- [`client/`](client/README.md) — React frontend for the search API
- [`legacy/`](legacy/README.md) — earlier Go/Rust prototypes (not maintained)

## Quickstart

```bash
uv sync                                                    # install workspace deps
uv run tuebingen-crawl                                     # 1. crawl pages → data/
uv run tuebingen-search index                              # 2. build index.bin
uv run tuebingen-search search -q "tübingen attractions"   # 3. query
```

For batch evaluation, the HTTP API, the web client, and all options, see the
component READMEs linked above (e.g. [`search/`](search/README.md)).