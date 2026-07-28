# Dev retrieval evaluation

20 queries, top-100 BM25F candidates, and
715 pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.5727 | 0.6023 | 0.9500 | 8.10 | 1.94 |
| bm25f-proximity | 0.5636 | 0.5925 | 0.9500 | 8.15 | 4.73 |
| bm25f-semantic | 0.6441 | 0.7058 | 0.9375 | 8.55 | 65.89 |
| full | 0.6345 | 0.6982 | 0.9375 | 8.55 | 68.08 |

Semantic re-ranking gains
0.0714 nDCG@10 and
0.1035 nDCG@20.
Proximity reduces both nDCG scores.

These pooled results are for development.
