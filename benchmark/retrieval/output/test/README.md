# Test retrieval evaluation

10 queries, top-100 BM25F candidates, and
267 pooled relevance judgments.

| Variant | nDCG@10 | nDCG@20 | MRR@10 | Positive@10 | API ms |
|---|---:|---:|---:|---:|---:|
| bm25f | 0.6078 | 0.6601 | 0.8111 | 5.60 | 2.06 |
| selected | 0.6690 | 0.7677 | 0.8750 | 6.30 | 67.62 |

Semantic re-ranking gains
0.0612 nDCG@10 and
0.1076 nDCG@20.
The selected configuration was frozen before this test run.
