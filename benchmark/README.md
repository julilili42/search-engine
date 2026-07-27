# Retrieval benchmark

Four variants are evaluated on the same queries and relevance judgments:
BM25F, BM25F + proximity, BM25F + semantic re-ranking, and both combined.

- `data/`: queries and qrels
- `src/`: retrieval and metric code
- `output/`: ablation results

Run from the repository root:

```bash
uv run python -m retrieval_benchmark.run_ablation
# Review output/judging_pool.tsv and update data/qrels.tsv.
uv run python -m retrieval_benchmark.summarize_ablation
```
