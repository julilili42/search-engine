# Crawl language benchmark

Offline check for predominantly German pages among the HTML documents stored in
the crawl database. It does not import or modify the live crawler.

```bash
uv run crawl-benchmark
```

Inputs default to `data/db/pages.sqlite` and the repository root. Outputs are
written to `benchmark/crawl/output/`:

- `pages.csv`: one auditable decision per stored page
- `summary.json`: aggregate counts and the exact decision rule

Visible text is extracted with Selectolax and split into language segments by
the offline Lingua detector in low-accuracy mode for long text, restricted to
German and English. A page is `german` when at least 50% of its classified
words are German. Pages with fewer than 20 classified words are `uncertain`;
all others are `not_german`. Other languages are outside this binary audit and
must be identified in the later manual sample.

Use explicit paths to run it on another immutable crawl snapshot:

```bash
uv run crawl-benchmark \
  --database /path/to/pages.sqlite \
  --root /path/to/snapshot \
  --output /path/to/output
```
