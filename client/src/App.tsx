import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react"
import { Search, Loader2, ExternalLink, Home, CircleAlert, SearchX, ChevronLeft, ChevronRight } from "lucide-react"

import Scene, { type Phase } from "@/galaxy/Scene"
import { CATEGORY_X_LABEL, CATEGORY_Y_LABEL } from "@/galaxy/categories"
import { PAGE_SIZE } from "@/galaxy/ResultStars"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { SearchResult } from "@/types"

// keep in sync with WARP_DURATION in galaxy/Scene.tsx so results never arrive
// before the camera has finished accelerating in
const MIN_WARP_MS = 1750
// fetch enough results up front to cover a few pages of pagination, so paging
// right/left is just a camera pan over already-fetched stars, not a re-fetch
const RESULTS_FETCH_COUNT = PAGE_SIZE * 3
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
  const [page, setPage] = useState(0)
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
    const params = new URLSearchParams({ q, top_n: String(RESULTS_FETCH_COUNT) })
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
    setPage(0)

    const start = Date.now()
    try {
      const res = await fetch(searchUrl(q, categoryX, categoryY))
      if (!res.ok) throw new Error(`Suche fehlgeschlagen (HTTP ${res.status})`)
      const data: SearchResult[] = await res.json()
      // set results as soon as they're known (even though we're still
      // warping) so ResultStars mounts and warms up its GPU buffers/shaders
      // ahead of time, instead of doing that work in the same frame the
      // reveal happens — that's what caused the stutter at the transition
      setResults(data)

      const remaining = MIN_WARP_MS - (Date.now() - start)
      if (remaining > 0) await sleep(remaining)

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
    setPage(0)
  }

  const totalPages = Math.ceil(results.length / PAGE_SIZE)
  const pagedResults = results.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  function goToPage(delta: number) {
    setPage((p) => Math.min(Math.max(p + delta, 0), totalPages - 1))
  }

  const showList = phase === "results" && results.length > 0
  // the results panel only has something to show once a search has landed
  // (a list, an error, or "no results") — before that, or once we've warped
  // back out to the galaxy, it stays off-screen and only the search bar floats
  const panelOpen = phase !== "idle" || searched

  return (
    <div className="relative h-svh w-svw overflow-hidden bg-[#05060d] text-white">
      <main className="absolute inset-0">
        <Scene phase={phase} results={results} page={page} totalPages={totalPages} onPageDelta={goToPage} />
        {flashNonce > 0 && (
          <div
            key={flashNonce}
            className="pointer-events-none absolute inset-0 bg-white opacity-0 [animation:warp-flash_0.6s_ease-out_forwards]"
          />
        )}
        {showList && totalPages > 1 && (
          <>
            <button
              type="button"
              onClick={() => goToPage(-1)}
              disabled={page === 0}
              title="Previous 10 results"
              className="absolute top-1/2 left-[25rem] flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 backdrop-blur-sm transition-colors enabled:hover:bg-white/20 disabled:opacity-0"
            >
              <ChevronLeft className="size-5" />
            </button>
            <button
              type="button"
              onClick={() => goToPage(1)}
              disabled={page >= totalPages - 1}
              title="Next 10 results"
              className="absolute top-1/2 right-4 flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 backdrop-blur-sm transition-colors enabled:hover:bg-white/20 disabled:opacity-0"
            >
              <ChevronRight className="size-5" />
            </button>
          </>
        )}
        {phase === "results" && (
          <div className="pointer-events-none absolute top-4 right-4 bottom-4 left-[25rem] text-[11px] tracking-wide text-white/40 uppercase">
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

      <aside
        className={`absolute top-0 left-0 z-10 flex h-full w-96 flex-col gap-2 overflow-hidden border-r border-white/10 bg-black/30 p-5 pt-24 backdrop-blur-sm transition-transform duration-500 ease-out ${
          panelOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {error && (
          <div className="flex shrink-0 items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            <CircleAlert className="size-4 shrink-0" />
            {error}
          </div>
        )}

        <div className="flex-1 space-y-2 overflow-y-auto">
          {searched && !loading && !error && results.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-white/50">
              <SearchX className="size-7" />
              <p className="text-sm">No results found.</p>
            </div>
          )}

          {showList &&
            pagedResults.map((result) => (
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

      <div className="absolute top-5 left-5 z-20 w-96">
        <h1 className="mb-2 text-base leading-tight font-semibold tracking-tight drop-shadow-md">Tübingen Search</h1>

        <form
          onSubmit={handleSearch}
          className="flex h-11 shrink-0 items-center gap-1 rounded-full border border-white/15 bg-black/50 pr-1.5 pl-1.5 backdrop-blur-sm focus-within:ring-2 focus-within:ring-white/30"
        >
          <button
            type="button"
            onClick={goBack}
            disabled={phase === "idle"}
            title="Back to galaxy"
            className="flex size-8 shrink-0 items-center justify-center rounded-full text-white/70 transition-colors enabled:hover:bg-white/10 enabled:hover:text-white disabled:cursor-default disabled:opacity-40"
          >
            <Home className="size-4" />
          </button>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Tübingen..."
            autoFocus
            disabled={loading}
            className="h-8 flex-1 border-0 bg-transparent px-1 text-sm text-white shadow-none placeholder:text-white/40 focus-visible:ring-0"
          />
          <Button
            type="submit"
            disabled={loading || !query.trim()}
            size="sm"
            className="size-8 shrink-0 rounded-full p-0"
          >
            {loading ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
          </Button>
        </form>
      </div>
    </div>
  )
}

export default App
