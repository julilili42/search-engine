# Decisions

Reusable notes for the final report.

## Template

### Title

- Status:
- Scope:
- Decision:
- Why:
- Expected effect:
- Evaluation:
- Report note:

## Search decisions

### Remove English stopwords

- Status: evaluated
- Scope: `search` tokenizer, `benchmark` qrels/runs
- Decision: Remove English stopwords during tokenization, while keeping negations such as `not`, `no`, and `nor`.
- Why: Frequent function words add noise and usually do not express the search intent.
- Expected effect: Cleaner query terms and less BM25 noise for English queries.
- Evaluation: Compare `benchmark/runs/crawl-20260707-1558/20260709-133333-stopwords.json` against the BM25 baseline.
- Report note: Stopword filtering improves query specificity without changing the public search API.

### Add query token proximity score

- Status: implemented
- Scope: `search` ranking, `benchmark` evaluation
- Decision: Add a small ranking bonus when all query terms occur close together in a document.
- Why: Nearby query terms are more likely to describe one relevant context than scattered term matches.
- Expected effect: Better ordering for multi-word queries, mainly when BM25 scores are close.
- Evaluation: Save a new benchmark run and compare it against the stopword run with `nDCG@10`, `nDCG@20`, `MRR@10`, and `Positives@10`.
- Report note: Proximity scoring extends BM25 with a weak, measurable relevance signal.
