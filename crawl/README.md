# Crawl

Link crawler that discovers English, Tübingen-related web pages and stores them
locally. Each page is scored for topical relevance, lexical Tübingen cues refined
by a DistilBERT semantic check, and near-duplicates are dropped via SimHash. It
respects `robots.txt` and is resumable: re-running picks up where a previous run
stopped.

## Setup

```bash
uv sync
```

(Workspace member — run from the repo root.)

## Usage

```bash
uv run tuebingen-crawl
```

- Seeds are configured in `crawl/seeds.toml` — one `[[sites]]` entry per seed
  with `url`, `request_delay`, and an optional `max_pages_per_seed` (omit to
  crawl until the frontier is exhausted).
- HTML is saved under `data/<host>/`; page metadata is recorded in
  `data/pages.sqlite`.
- Crawl state is persisted per host, so an interrupted crawl resumes on the next
  run.
