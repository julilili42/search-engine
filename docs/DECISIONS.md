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

### Embedding-based second-stage re-ranking

- Status: implemented, evaluation pending
- Scope: `search` ranking, new `embed` command, `benchmark` evaluation
- Decision: Re-rank the top-100 lexical candidates with a convex combination of the min-max-normalized lexical score and the embedding cosine similarity: `alpha * lexical + (1 - alpha) * cosine`, `alpha = 0.5`. The proximity bonus stays inside the lexical score (BM25TP-style additive integration, Rasolofo & Savoy 2003) rather than becoming a third fusion signal. Documents are embedded offline (`uv run embed`) with `paraphrase-MiniLM-L6-v2`; a missing or stale embeddings file falls back to pure lexical ranking.
- Why: BM25 cannot match synonyms or paraphrases ("where to eat" vs "restaurant"); embeddings close that gap. Convex combination was chosen over reciprocal rank fusion because it outperforms RRF in- and out-of-domain, needs only one parameter, and is sample-efficient to tune on a small query set (Bruch, Gai & Ingber, ACM TOIS 2023). The model is paraphrase/STS-trained, not fine-tuned on a retrieval dataset, and runs strictly as a second stage over the classical first stage, as the project rules require.
- Expected effect: Better ordering for queries whose wording differs from the page wording; unchanged behavior for exact-term queries.
- Evaluation: Benchmark run vs the proximity baseline (`nDCG@10`, `nDCG@20`, `MRR@10`); tune `alpha` over {0.3, 0.5, 0.7} and compare an RRF variant as a sanity check.
- Report note: Hybrid retrieval — a self-implemented classical first stage retrieves candidates, a semantic second stage re-ranks them.
