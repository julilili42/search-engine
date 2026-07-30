# Client

Minimal React + TypeScript frontend (Vite, Tailwind v4, shadcn/ui) for the
`/search` endpoint of the FastAPI app.

## Setup

```bash
cd client
npm install
```

## Usage

Start the backend from the repo root (default port 8000):

```bash
uv run uvicorn tuebingen_search.api:app
```

Then run the dev server:

```bash
cd client
npm run dev
```

The dev server runs on http://localhost:5173 and proxies `/search`, `/batch`,
and `/health` to `http://127.0.0.1:8000` (see `vite.config.ts`), so no backend
CORS is needed. Use a custom index with
`INDEX_PATH=/path/to/index.bin uv run uvicorn ...`.
