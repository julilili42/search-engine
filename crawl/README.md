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
uv run crawl --seeds crawl/seeds.pilot.toml --data-dir data/pilot-20260715
```

- Seeds live in `crawl/seeds.toml`.
- Sitemaps declared in `robots.txt` are loaded once for each seed origin.
- All hosts use the global `Config` request delay, timeout, and retry settings.
- Workers claim URLs from one global frontier. It picks the highest-scoring
  eligible host while allowing at most one in-flight request per host.
- HTML is saved under `data/html/<host>/`; logs are written to
  `data/log/crawl.log`; global state is saved as
  `data/state/crawl_state.json`; page and link metadata is recorded in
  `data/db/pages.sqlite`.
- Saved pages are capped globally and per host. Hosts with repeated rejects and
  no saved pages are stopped early.

## Crawler Flow

1. `main.py` loads seeds, models, stores, and crawl config.
2. `crawl_runner.py` creates one global frontier and workers claim leases from it.
3. `lease_processor.py` processes each lease, checks host budgets and `robots.txt`,
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
