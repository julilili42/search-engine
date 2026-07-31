# Dev retrieval evaluation

20 queries, top-100 BM25F candidates, and
1209 pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.5434 | 0.5394 | 0.9250 | 8.15 | 2.01 |
| bm25f-proximity | 0.5310 | 0.5308 | 0.9167 | 8.15 | 15.30 |
| bm25f-semantic | 0.6260 | 0.6252 | 0.9375 | 8.55 | 56.12 |
| full | 0.6061 | 0.6191 | 0.9333 | 8.55 | 59.33 |

Semantic re-ranking gains
0.0826 nDCG@10 and
0.0858 nDCG@20.
Proximity reduces both nDCG scores.

These pooled results are for development.
