# Dev retrieval evaluation

20 queries, top-100 BM25F candidates, and
755 pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.5250 | 0.5436 | 0.9350 | 8.05 | 1.79 |
| bm25f-proximity | 0.5042 | 0.5327 | 0.9017 | 8.00 | 15.61 |
| bm25f-semantic | 0.5953 | 0.6652 | 0.9375 | 8.50 | 57.37 |
| full | 0.5849 | 0.6577 | 0.9375 | 8.50 | 57.22 |

Semantic re-ranking gains
0.0702 nDCG@10 and
0.1216 nDCG@20.
Proximity reduces both nDCG scores.

These pooled results are for development.
