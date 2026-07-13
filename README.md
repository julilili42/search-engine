# Tübingen Search Engine

> A custom search engine with link crawling and an indexing pipeline and client frontend.

## Components

This repo is a uv workspace with separate components:

- [`crawl/`](crawl/README.md) — link crawler that fetches and stores pages
- [`search/`](search/README.md) — BM25 index, CLI, and FastAPI search API
- [`verdict-ml/`](verdict-ml/README.md) — PageVerdict and LinkVerdict runtime;
  training and model releases live in [labeling-lab](https://github.com/julilili42/labeling-lab)
- [`client/`](client/README.md) — React frontend for the search API

## Quickstart

Install dependencies:

```bash
uv sync
```

Choose a data source:

**Latest snapshot**

```bash
uv run data-fetch
```

**Crawl locally**

```bash
uv run crawl
uv run index
uv run embed
```

Search:

```bash
uv run search -q "tübingen attractions"
```

### Web UI

Start the API and client in separate terminals:

```bash
uv run uvicorn tuebingen_search.api:app
```

```bash
cd client
npm install  # once
npm run dev
```

Vite prints the local URL for the client.

For the crawl report, HTTP API, web client, and all options, see the component
READMEs linked above (e.g. [`search/`](search/README.md)).
