# Crawl

Focused crawler for English, Tübingen-related web pages. It fetches HTML pages,
scores pages and links with the `verdict-ml` PageVerdict/LinkVerdict models,
drops near-duplicates via SimHash, respects `robots.txt`, and persists crawl
state so interrupted runs can resume.

## Setup

```bash
uv sync
```

Run commands from the repository root.

## Usage

```bash
uv run crawl
uv run crawl report --db data/pages.sqlite
uv run crawl --seeds crawl/seeds.pilot.toml --data-dir data/pilot-20260715
```

- Seeds live in `crawl/seeds.toml`.
- Each `[[sites]]` entry supports `url`, `request_delay`, optional
  `max_pages_per_seed`, `max_discovered_per_seed`, and `sitemap = true` for
  opt-in same-origin sitemap discovery (`robots.txt`, then `/sitemap.xml`).
- Workers claim URLs from one global frontier. It picks the highest-scoring
  eligible host while allowing at most one in-flight request per host.
- HTML is saved under `data/html/<host>/`; global state is saved as
  `data/state/global_frontier.json`, with deduplication state in
  `data/state/global_seen.json`; page and link metadata is recorded in
  `data/pages.sqlite`.
- Saved pages are capped per host, and hosts with repeated rejects and no saved
  pages are stopped early.

## Crawler Flow

1. `main.py` loads seeds, models, stores, and crawl config.
2. `scheduler.py` creates one global frontier and workers claim leases from it.
3. `crawler.py` processes each lease, checks host budgets and `robots.txt`,
   then fetches pages.
4. `page_evaluation.py` parses, classifies, saves, or rejects pages.
5. `link_evaluation.py` classifies links from saved pages and selects which
   links enter the frontier.
6. `frontier.py` owns global priority, host politeness, saved-page caps, and
   host reject budgets.

## Stored Metadata

PageVerdict fields are stored for saved and rejected pages:

```text
pageverdict_score
pageverdict_label
pageverdict_decision
pageverdict_model
pageverdict_snippet
```

Link candidates are stored with parent page context, anchor/target metadata,
LinkVerdict score/label/model, enqueue/selection decisions, rejection reasons,
and target page outcome metadata (`target_status`, target PageVerdict fields,
target rejection reason, etc.).
