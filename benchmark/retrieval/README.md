# Retrieval benchmark

Four variants are evaluated on the same queries and relevance judgments:
BM25F, BM25F + proximity, BM25F + semantic re-ranking, and both combined.

- `data/dev/`: development queries and relevance judgments
- `data/test/`: sealed test queries
- `output/`: generated runs and metrics

One command, three operations:

```bash
uv run retrieval-benchmark run dev
uv run retrieval-benchmark score dev
uv run retrieval-benchmark sweep
uv run retrieval-benchmark run test
uv run retrieval-benchmark score test
```
