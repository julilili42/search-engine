# Test retrieval evaluation

10 queries, top-100 BM25F candidates, and
530 pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.4867 | 0.5002 | 0.8250 | 5.20 | 2.10 |
| selected | 0.5300 | 0.5989 | 0.8500 | 5.70 | 79.40 |

Semantic re-ranking gains
0.0433 nDCG@10 and
0.0987 nDCG@20.
The selected configuration was frozen before this test run.
