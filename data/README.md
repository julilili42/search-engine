# Data

Search requires `db/pages.sqlite` and `index/index.bin`. `embeddings/embeddings.npz`
enables semantic re-ranking. Crawl logs are written to `log/crawl.log`.

Create them locally with `uv run crawl`, `uv run index`, and `uv run embed`, or download the
latest tested snapshot with:

```bash
uv run data-fetch
```
