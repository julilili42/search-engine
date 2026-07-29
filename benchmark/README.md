# Benchmarks

Run all commands from any directory inside the repository.

## Crawl language audit

```bash
uv run crawl-benchmark
```

Classifies all stored pages and prints aggregate language counts. Outputs:
`crawl/output/pages.csv` and `crawl/output/summary.json`. Runtime: about
2--3 minutes.

## Index storage

```bash
uv run index-storage-benchmark
```

Builds the filtered index and prints the MessagePack/JSON size and load-time
comparison. Outputs: `index_storage/output/`. Runtime: about 14 minutes.
Use `--limit 500 --repeats 3` for a quick check.

## Retrieval

```bash
uv run retrieval-benchmark run dev
uv run retrieval-benchmark score dev
uv run retrieval-benchmark run test
uv run retrieval-benchmark score test
```

`run` writes ranked runs and judging pools. `score` requires complete qrels,
prints the metric table, and updates the corresponding `output/` directory.
The frozen fusion weights default to `alpha=0.4` and `beta=0.6`.
