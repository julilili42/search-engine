# Retrieval ablation

All variants use the same 20 queries, top-100 BM25F candidates, and 466 pooled
top-20 judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.7038 | 0.8103 | 0.9500 | 8.10 | 1.90 |
| bm25f-proximity | 0.6958 | 0.8002 | 0.9500 | 8.15 | 18.13 |
| bm25f-semantic | 0.7342 | 0.8441 | 0.9750 | 8.40 | 64.64 |
| full | 0.7183 | 0.8395 | 0.9750 | 8.35 | 64.77 |

Semantic re-ranking without proximity performs best, adding
0.0304 nDCG@10 and 0.0338 nDCG@20 over BM25F.
Proximity reduces both nDCG scores.

Judgments are single-assessor Codex ratings from retrieved metadata. These
pooled results are diagnostic, not an unbiased generalization estimate.
