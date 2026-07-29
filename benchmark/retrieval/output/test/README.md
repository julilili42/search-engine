# Test retrieval evaluation

10 queries, top-100 BM25F candidates, and
308 pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.5382 | 0.5798 | 0.8600 | 4.90 | 1.88 |
| selected | 0.5965 | 0.6807 | 0.8700 | 5.90 | 58.44 |

Semantic re-ranking gains
0.0583 nDCG@10 and
0.1009 nDCG@20.
The selected configuration was frozen before this test run.
