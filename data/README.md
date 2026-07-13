# Data

Search requires `pages.sqlite` and `index.bin` in this directory. `embeddings.npz` enables semantic re-ranking.

Create them locally with `uv run crawl`, `uv run index`, and `uv run embed`, or download the
latest tested snapshot with:

```bash
uv run data-fetch
```
