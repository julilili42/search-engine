# Tübingen Search – Client

Minimales React + TypeScript Frontend (Vite, Tailwind v4, shadcn/ui), das den
`/search` Endpunkt der FastAPI-Anwendung anspricht.

## Setup

```bash
cd client
npm install
```

## Entwicklung

Zuerst das Backend starten (Default-Port 8000), aus dem **Projekt-Root**:

```bash
# im Projekt-Root – nutzt automatisch ./index.bin
uv run uvicorn tuebingen_search.api:app
```

Für einen abweichenden Index-Pfad: `INDEX_PATH=/pfad/zu/index.bin uv run uvicorn ...`.

Dann den Dev-Server:

```bash
cd client
npm run dev
```

Der Vite-Dev-Server läuft auf http://localhost:5173 und leitet Anfragen an
`/search` und `/health` per Proxy an `http://127.0.0.1:8000` weiter (siehe
`vite.config.ts`), sodass kein CORS im Backend nötig ist.
