# Labeling

Manual labeling UI for PageVerdict and LinkVerdict training data.

Data is stored in `labeling/data/labeling.sqlite`.

Run the UI:

```bash
uv run labeling
```

```text
http://127.0.0.1:8010
```

Serper search needs:

```bash
export SERPER_API_KEY="..."
```

Import crawler candidates:

```bash
uv run export-pageverdict
uv run export-link-candidates
```

Then import in the UI:

- `data/pageverdict_candidates.jsonl` for fresh crawler decisions
- `data/link_candidates.jsonl` in `Links` mode for link-follow decisions

Ratings:

- `1`: reject
- `2`: bad
- `3`: unsure
- `4`: good
- `5`: great

The API maps `1-2` to `negative`, `3` to `skip`, and `4-5` to `positive`.

Exports:

- `http://127.0.0.1:8010/api/export/serp-labels.jsonl`
- `http://127.0.0.1:8010/api/export/link-labels.jsonl`

Starter queries live in `labeling/queries/tuebingen_serp_queries.txt`.
