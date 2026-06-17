# Tübingen Search Engine

> A custom search engine with link crawling and an indexing pipeline and client frontend.

## Usage

### 1. Crawl

```bash
uv run tuebingen-crawl
```

The URLs to crawl are defined in `crawl/seeds.toml` (one `[[sites]]` entry per seed, with `max_pages` and `request_delay`). Pages are saved as HTML to `save_dir` (default `../data`, one subfolder per host).

### 2. Build the index

```bash
uv run tuebingen-search index 
```

### 3. Search

```bash
uv run tuebingen-search search -q "boris palmer" -t 5
```

`-q` query (required), `-i` index file (default `index.bin`), `-t` number of results (default 10).


### 4. Batch Search
Runs many queries at once and writes a ranked result file for evaluation.

```bash
uv run tuebingen-search batch -b queries.tsv -o results.tsv -t 100
```

`-b` input file (default `queries.tsv`), `-o` output file (default `results.tsv`),
`-i` index file (default `index.bin`), `-t` results per query (default 100).

**Input** — tab-separated, one query per line (`query-id`, `query text`):

```
1	tübingen attractions
2	food and drinks
```

**Output** — tab-separated, one ranked result per line (`query-id`, `rank`, `url`, `score`):

```
1	1	https://www.tuebingen.de/en/3521.html	0.7250
1	2	https://www.komoot.com/guide/355570/...	0.6710
```

### 5. Client Frontend
Start backend via

```bash
uv run uvicorn tuebingen_search.api:app
```

and in `client/` the frontend with

```bash
npm run dev
```