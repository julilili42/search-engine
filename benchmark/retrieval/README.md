# Retrieval benchmark

Four variants are evaluated on the same queries and relevance judgments:
BM25F, BM25F + proximity, BM25F + semantic re-ranking, and both combined.

- `data/dev/`: development queries and relevance judgments
- `data/test/`: sealed test queries
- `output/`: generated runs plus retained metrics and provenance manifests

One command, three operations:

```bash
uv run retrieval-benchmark run dev
uv run retrieval-benchmark score dev
uv run retrieval-benchmark sweep
uv run retrieval-benchmark run test
uv run retrieval-benchmark score test
```

`sweep` reweights the saved development runs. Runs and judging pools are
regenerable and ignored; the compact result files are kept for the submission.
