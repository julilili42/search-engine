# Dev retrieval evaluation

20 queries, top-100 BM25F candidates, and
788 pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.5250 | 0.5412 | 0.9350 | 8.05 | 1.79 |
| bm25f-proximity | 0.5042 | 0.5304 | 0.9017 | 8.00 | 15.61 |
| bm25f-semantic | 0.5953 | 0.6619 | 0.9375 | 8.50 | 57.37 |
| full | 0.5849 | 0.6543 | 0.9375 | 8.50 | 57.22 |

Semantic re-ranking gains
0.0702 nDCG@10 and
0.1206 nDCG@20.
Proximity reduces both nDCG scores.

These pooled results are for development.
