# Tübingen Search Engine

> A custom search engine with link crawling and an indexing pipeline and client frontend.

## Components

This repo is a uv workspace with separate components:

- [`crawl/`](crawl/README.md) — link crawler that fetches and stores pages
- [`search/`](search/README.md) — BM25 index, CLI, and FastAPI search API
- [`verdict-ml/`](verdict-ml/README.md) — PageVerdict and LinkVerdict training
- [`labeling/`](labeling/README.md) — manual relevance labeling UI
- [`client/`](client/README.md) — React frontend for the search API

## Quickstart

```bash
uv sync                                                    # install workspace deps
uv run crawl                                               # 1. crawl pages -> data/
uv run index                                               # 2. build index.bin
uv run search -q "tübingen attractions"                    # 3. query
```

For the crawl report, HTTP API, web client, and all options, see the component
READMEs linked above (e.g. [`search/`](search/README.md)).
