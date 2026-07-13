# Crawl benchmark

Passively monitors a running crawl by reading `data/pages.sqlite` and writing
JSONL snapshots. It does not import or modify crawler code.

## Usage

Run commands from the repository root:

```bash
python3 benchmark/crawl/monitor.py              # snapshot every 60s
python3 benchmark/crawl/monitor.py --once       # one snapshot
python3 benchmark/crawl/monitor.py --status     # live status as JSON
```

`--status` measures activity over a short window (15s by default) and reports
totals, `crawler_active`, and `pages_per_minute`. Snapshots are written to
`metrics/` and are ignored by Git.
