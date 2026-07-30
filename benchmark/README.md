# Benchmarks

Run all commands from any directory inside the repository.

## Crawl language audit

```bash
uv run crawl-benchmark
```

Classifies all stored pages and prints aggregate language counts. Outputs:
`crawl/output/pages.csv` and `crawl/output/summary.json`. Runtime: about
2--3 minutes. The page-level CSV is generated locally; the compact summary is
kept as the submission result.

## Index storage

```bash
uv run index-storage-benchmark
```

Builds the filtered index and prints the MessagePack/JSON size and load-time
comparison. Runtime: about 14 minutes. The large index files are generated
locally; `index_storage/output/results.json` is kept as the submission result.
Use `--limit 500 --repeats 3` for a quick check.

## Retrieval

```bash
uv run retrieval-benchmark run dev
uv run retrieval-benchmark score dev
uv run retrieval-benchmark sweep
uv run retrieval-benchmark run test
uv run retrieval-benchmark score test
```

`run` writes ranked runs and judging pools. `score` requires complete qrels,
prints the metric table, and updates the corresponding `output/` directory.
`sweep` reweights the saved development runs. Generated runs and judging pools
are ignored; compact metrics and provenance manifests are retained. The frozen
fusion weights default to `alpha=0.4` and `beta=0.6`.
