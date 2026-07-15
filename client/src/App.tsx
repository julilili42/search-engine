import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import { Search, Loader2, ExternalLink, Sparkles, CircleAlert, SearchX, ArrowLeft } from "lucide-react"

import Scene, { type Phase } from "@/galaxy/Scene"
import { CATEGORY_X_LABEL, CATEGORY_Y_LABEL } from "@/galaxy/categories"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { SearchResult } from "@/types"

// keep in sync with WARP_DURATION in galaxy/Scene.tsx so results never arrive
// before the camera has finished accelerating in
const MIN_WARP_MS = 1750
const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

function displayHost(result: SearchResult) {
  if (!result.url) return "local file"
  try {
    return new URL(result.url).hostname.replace(/^www\./, "")
  } catch {
    return result.url
  }
}

function App() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)
  const [phase, setPhase] = useState<Phase>("idle")
  const [flashNonce, setFlashNonce] = useState(0)
  const [categoryX, setCategoryX] = useState(CATEGORY_X_LABEL)
  const [categoryY, setCategoryY] = useState(CATEGORY_Y_LABEL)
  const prevPhase = useRef<Phase>("idle")

  useEffect(() => {
    if (prevPhase.current === "warping" && phase === "results") {
      setFlashNonce((n) => n + 1)
    }
    prevPhase.current = phase
  }, [phase])

  function searchUrl(q: string, catX: string, catY: string) {
    const params = new URLSearchParams({ q, top_n: "10" })
    // only send overrides when they actually differ, so the backend can keep
    // using its cached default axis embeddings for the common case
    if (catX !== CATEGORY_X_LABEL || catY !== CATEGORY_Y_LABEL) {
      params.set("cat_x", catX)
      params.set("cat_y", catY)
    }
    return `/search?${params}`
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    const q = query.trim()
    if (!q || loading) return

    setPhase("warping")
    setLoading(true)
    setError(null)

    const start = Date.now()
    try {
      const res = await fetch(searchUrl(q, categoryX, categoryY))
      if (!res.ok) throw new Error(`Suche fehlgeschlagen (HTTP ${res.status})`)
      const data: SearchResult[] = await res.json()

      const remaining = MIN_WARP_MS - (Date.now() - start)
      if (remaining > 0) await sleep(remaining)

      setResults(data)
      setSearched(true)
      setPhase(data.length > 0 ? "results" : "idle")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler")
      setResults([])
      setSearched(true)
      setPhase("idle")
    } finally {
      setLoading(false)
    }
  }

  // re-split the current results onto a new pair of category axes, in place —
  // no warp, no re-fetch of the search itself, just a fresh layout
  async function applyCategories(catX: string, catY: string) {
    const q = query.trim()
    if (!q || phase !== "results") return
    try {
      const res = await fetch(searchUrl(q, catX, catY))
      if (!res.ok) return
      const data: SearchResult[] = await res.json()
      setResults(data)
    } catch {
      // keep the previous layout if the recategorize request fails
    }
  }

  function handleAxisKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") event.currentTarget.blur()
  }

  function goBack() {
    setPhase("idle")
    setSearched(false)
    setResults([])
    setError(null)
  }

  const showList = phase === "results" && results.length > 0

  return (
    <div className="flex h-svh w-svw overflow-hidden bg-[#05060d] text-white">
      <aside className="flex w-96 shrink-0 flex-col gap-4 overflow-hidden border-r border-white/10 bg-black/30 p-5 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/10">
            <Sparkles className="size-4" />
          </div>
          <div>
            <h1 className="text-base leading-tight font-semibold tracking-tight">Tübingen Search</h1>
            <p className="text-xs text-white/50">BM25F + semantic re-ranking</p>
          </div>
        </div>

        <form onSubmit={handleSearch} className="relative shrink-0">
          <Search className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-white/40" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Tübingen..."
            autoFocus
            disabled={loading}
            className="h-11 rounded-full border-white/15 bg-white/5 pr-24 pl-10 text-sm text-white placeholder:text-white/40 focus-visible:ring-white/30"
          />
          <Button
            type="submit"
            disabled={loading || !query.trim()}
            size="sm"
            className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-full"
          >
            {loading ? <Loader2 className="animate-spin" /> : <Search />}
          </Button>
        </form>

        {error && (
          <div className="flex shrink-0 items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            <CircleAlert className="size-4 shrink-0" />
            {error}
          </div>
        )}

        {searched && !loading && !error && results.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-10 text-center text-white/50">
            <SearchX className="size-7" />
            <p className="text-sm">No results found.</p>
          </div>
        )}

        {!searched && !loading && (
          <p className="text-sm leading-relaxed text-white/40">
            Enter a query to warp through the galaxy and land on the top 10 results, placed as stars by relevance and
            topic.
          </p>
        )}

        <div className="flex-1 space-y-2 overflow-y-auto">
          {showList &&
            results.map((result) => (
              <a
                key={`${result.rank}-${result.path}`}
                href={result.url ?? undefined}
                target="_blank"
                rel="noreferrer"
                className="group block rounded-lg border border-white/10 bg-white/5 px-3 py-2 transition-colors hover:bg-white/10"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1.5 truncate text-sm font-medium">
                    <span className="text-white/40">{result.rank}.</span>
                    {displayHost(result)}
                  </span>
                  <ExternalLink className="size-3 shrink-0 text-white/40" />
                </div>
                <p className="mt-0.5 line-clamp-1 text-xs text-white/50 group-hover:line-clamp-2">
                  {result.snippet}
                </p>
              </a>
            ))}
        </div>
      </aside>

      <main className="relative flex-1 overflow-hidden">
        <Scene phase={phase} results={results} />
        {flashNonce > 0 && (
          <div
            key={flashNonce}
            className="pointer-events-none absolute inset-0 bg-white opacity-0 [animation:warp-flash_0.6s_ease-out_forwards]"
          />
        )}
        {phase !== "idle" && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={goBack}
            className="absolute top-4 left-4 gap-1.5 rounded-full bg-black/30 text-white/70 backdrop-blur-sm hover:bg-black/50 hover:text-white"
          >
            <ArrowLeft className="size-4" />
            Back to galaxy
          </Button>
        )}
        {phase === "results" && (
          <div className="pointer-events-none absolute inset-4 text-[11px] tracking-wide text-white/40 uppercase">
            <div className="pointer-events-auto absolute right-0 bottom-0 flex items-center gap-1.5">
              <input
                value={categoryX}
                onChange={(e) => setCategoryX(e.target.value)}
                onBlur={() => applyCategories(categoryX, categoryY)}
                onKeyDown={handleAxisKeyDown}
                title="Click to change the X axis category"
                className="w-56 bg-transparent text-right uppercase outline-none placeholder:text-white/30 focus:text-white/80"
              />
              <span>→</span>
            </div>
            <div className="pointer-events-auto absolute top-12 left-0 flex flex-col items-center gap-1.5">
              <span>↑</span>
              <input
                value={categoryY}
                onChange={(e) => setCategoryY(e.target.value)}
                onBlur={() => applyCategories(categoryX, categoryY)}
                onKeyDown={handleAxisKeyDown}
                title="Click to change the Y axis category"
                className="h-56 bg-transparent uppercase outline-none placeholder:text-white/30 focus:text-white/80 [writing-mode:vertical-rl]"
              />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

export default App
