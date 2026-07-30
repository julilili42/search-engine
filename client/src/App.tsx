import { useEffect, useRef, useState, type FormEvent } from "react"
import { Search, Loader2, ExternalLink, Home, CircleAlert, SearchX, ChevronLeft, ChevronRight, FileSpreadsheet, Download, Upload, X } from "lucide-react"

import Scene, { type Phase } from "@/galaxy/Scene"
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

function batchFormatError(data: string) {
  const ids = new Set<string>()
  const lines = data.split(/\r?\n/)
  if (!lines.some((line) => line.trim())) return "Paste at least one query."
  for (const [index, line] of lines.entries()) {
    if (!line.trim()) continue
    const [id, query, ...extra] = line.split("\t")
    if (!id || !query || extra.length) return `Line ${index + 1}: expected ID, tab and query.`
    if (!/^\d+$/.test(id.trim())) return `Line ${index + 1}: ID must be a number.`
    if (!query.trim()) return `Line ${index + 1}: query is empty.`
    if (ids.has(id.trim())) return `Line ${index + 1}: duplicate ID ${id.trim()}.`
    ids.add(id.trim())
  }
  return null
}

function displayUrl(result: SearchResult) {
  if (!result.url) return "local file"
  try {
    const url = new URL(result.url)
    return `${url.hostname.replace(/^www\./, "")}${url.pathname === "/" ? "" : url.pathname}`
  } catch {
    return result.url
  }
}

function displayTitle(result: SearchResult) {
  if (result.title) return result.title
  if (!result.url) return result.path.split("/").pop() || "Search result"
  try {
    const slug = new URL(result.url).pathname.split("/").filter(Boolean).pop()
    return slug ? decodeURIComponent(slug).replace(/[-_]+/g, " ") : displayUrl(result)
  } catch {
    return displayUrl(result)
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
  const [categoryX, setCategoryX] = useState("")
  const [categoryY, setCategoryY] = useState("")
  const [batchText, setBatchText] = useState("")
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchError, setBatchError] = useState<string | null>(null)
  const batchDialog = useRef<HTMLDialogElement>(null)
  const prevPhase = useRef<Phase>("idle")
  const phaseRef = useRef<Phase>("idle")
  const categoryRequest = useRef(0)

  useEffect(() => {
    if (prevPhase.current === "warping" && phase === "results") {
      setFlashNonce((n) => n + 1)
    }
    prevPhase.current = phase
    phaseRef.current = phase
  }, [phase])

  useEffect(() => {
    if (phase !== "results") return
    const timer = setTimeout(() => void applyCategories(categoryX, categoryY), 350)
    return () => clearTimeout(timer)
  }, [categoryX, categoryY])

  function searchUrl(q: string, catX: string, catY: string) {
    const params = new URLSearchParams({ q, top_n: String(RESULTS_FETCH_COUNT) })
    if (catX.trim()) params.set("cat_x", catX.trim())
    if (catY.trim()) params.set("cat_y", catY.trim())
    return `/search?${params}`
  }

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    const q = query.trim()
    if (!q || loading) return

    setPhase("warping")
    phaseRef.current = "warping"
    categoryRequest.current += 1
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
    if (!q || phaseRef.current !== "results") return
    const request = ++categoryRequest.current
    try {
      const res = await fetch(searchUrl(q, catX, catY))
      if (!res.ok) return
      const data: SearchResult[] = await res.json()
      if (request === categoryRequest.current) setResults(data)
    } catch {
      // keep the previous layout if the recategorize request fails
    }
  }

  function goBack() {
    setPhase("idle")
    phaseRef.current = "idle"
    categoryRequest.current += 1
    setSearched(false)
    setResults([])
    setError(null)
    setPage(0)
  }

  async function downloadBatch() {
    if (batchValidationError || batchLoading) {
      setBatchError(batchValidationError)
      return
    }
    setBatchLoading(true)
    setBatchError(null)
    try {
      const response = await fetch("/batch", {
        method: "POST",
        headers: { "Content-Type": "text/plain" },
        body: batchText,
      })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(body?.detail || `Batch search failed (HTTP ${response.status})`)
      }
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement("a")
      link.href = url
      link.download = "results.tsv"
      link.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setBatchError(err instanceof Error ? err.message : "Batch search failed")
    } finally {
      setBatchLoading(false)
    }
  }

  const totalPages = Math.ceil(results.length / PAGE_SIZE)
  const pagedResults = results.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
  const hasCategoryX = Boolean(categoryX.trim())
  const hasCategoryY = Boolean(categoryY.trim())
  const batchValidationError = batchFormatError(batchText)

  function goToPage(delta: number) {
    setPage((p) => Math.min(Math.max(p + delta, 0), totalPages - 1))
  }

  const showList = phase === "results" && results.length > 0
  // the results panel slides in once the stars are actually on screen (or a
  // search has landed on an error / zero results) — not while still warping,
  // so it doesn't beat the reveal it's meant to accompany
  const panelOpen = phase === "results" || (searched && !loading)

  return (
    <div className="relative h-svh w-svw overflow-hidden bg-[#05060d] text-white">
      <main className="absolute inset-0">
        <Scene
          phase={phase}
          results={results}
          page={page}
          totalPages={totalPages}
          onPageDelta={goToPage}
          hasCategoryX={hasCategoryX}
          hasCategoryY={hasCategoryY}
        />
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
              className="absolute top-1/2 left-[31rem] flex size-10 -translate-y-1/2 items-center justify-center rounded-full bg-white/10 backdrop-blur-sm transition-colors enabled:hover:bg-white/20 disabled:opacity-0"
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
          <div className="pointer-events-none absolute top-4 right-4 bottom-4 left-[31rem] text-[11px] tracking-wide text-white/40 uppercase">
            <div className="pointer-events-auto absolute right-0 bottom-0 flex items-center gap-1.5">
              <input
                value={categoryX}
                onChange={(e) => setCategoryX(e.target.value)}
                title="Click to change the X axis category"
                placeholder="X category"
                className="w-56 border-b-2 border-indigo-300/80 bg-transparent px-1.5 py-1.5 text-right text-xs font-semibold tracking-[0.14em] text-white/90 uppercase drop-shadow-[0_0_5px_rgba(165,180,252,0.45)] outline-none transition placeholder:text-white/60 hover:border-indigo-100 focus:border-white focus:text-white focus:drop-shadow-[0_0_8px_rgba(165,180,252,0.9)]"
              />
              <span>→</span>
            </div>
            <div className="pointer-events-auto absolute top-12 left-0 flex flex-col items-center gap-1.5">
              <span>↑</span>
              <input
                value={categoryY}
                onChange={(e) => setCategoryY(e.target.value)}
                title="Click to change the Y axis category"
                placeholder="Y category"
                className="h-56 border-l-2 border-indigo-300/80 bg-transparent px-1.5 py-1.5 text-xs font-semibold tracking-[0.14em] text-white/90 uppercase drop-shadow-[0_0_5px_rgba(165,180,252,0.45)] outline-none transition placeholder:text-white/60 hover:border-indigo-100 focus:border-white focus:text-white focus:drop-shadow-[0_0_8px_rgba(165,180,252,0.9)] [writing-mode:vertical-rl]"
              />
            </div>
          </div>
        )}
      </main>

      <aside
        className={`absolute top-0 left-0 z-10 flex h-full w-[30rem] flex-col gap-2 overflow-hidden border-r border-white/10 bg-black/15 p-5 pt-20 transition-transform duration-500 ease-out ${
          panelOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {error && (
          <div className="flex shrink-0 items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            <CircleAlert className="size-4 shrink-0" />
            {error}
          </div>
        )}

        <div className="galaxy-scrollbar min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          {searched && !loading && !error && results.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-white/50">
              <SearchX className="size-7" />
              <p className="text-sm">No results found.</p>
            </div>
          )}

          {showList && (
            <div className="grid gap-2">
              {pagedResults.map((result) => (
              <a
                key={`${result.rank}-${result.path}`}
                href={result.url ?? undefined}
                target="_blank"
                rel="noreferrer"
                className="group flex flex-col justify-center rounded-lg border border-white/10 bg-white/5 px-3 py-2 transition-colors hover:bg-white/10"
              >
                <div className="flex items-start gap-1.5 text-[11px] text-white/45">
                  <span className="text-white/35">{result.rank}.</span>
                  <span className="min-w-0 break-all">{displayUrl(result)}</span>
                  <ExternalLink className="size-3 shrink-0 text-white/30" />
                </div>
                <h2 className="break-words text-sm font-medium text-white/90 group-hover:text-white group-hover:underline">
                  {displayTitle(result)}
                </h2>
                <p className="mt-0.5 line-clamp-2 text-xs leading-4 text-white/55">
                  {result.snippet}
                </p>
              </a>
              ))}
            </div>
          )}
        </div>
      </aside>

      <div className="absolute top-0 left-0 z-20 w-[30rem] p-5">
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

      {phase === "idle" && (
        <button
          type="button"
          onClick={() => {
            setBatchError(null)
            batchDialog.current?.showModal()
          }}
          className="absolute top-5 right-5 z-20 flex items-center gap-2 rounded-full border border-white/15 bg-black/40 px-3.5 py-2 text-xs font-medium text-white/65 backdrop-blur-md transition hover:border-indigo-300/50 hover:bg-white/10 hover:text-white"
        >
          <FileSpreadsheet className="size-4" />
          Batch search
        </button>
      )}

      <dialog
        ref={batchDialog}
        className="m-auto w-[min(36rem,calc(100vw-2rem))] rounded-2xl border border-white/15 bg-[#0b0d18]/95 p-0 text-white shadow-[0_24px_100px_rgba(0,0,0,0.75)] backdrop:bg-[#03040a]/75 backdrop:backdrop-blur-sm"
      >
        <div className="border-b border-white/10 px-5 py-4">
          <button
            type="button"
            onClick={() => batchDialog.current?.close()}
            title="Close"
            className="float-right flex size-8 items-center justify-center rounded-full text-white/45 transition hover:bg-white/10 hover:text-white"
          >
            <X className="size-4" />
          </button>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <FileSpreadsheet className="size-4 text-indigo-300" />
            Batch search
          </div>
        </div>
        <div className="p-5">
          <label className="mb-3 flex h-10 cursor-pointer items-center justify-center gap-2 rounded-xl border border-dashed border-indigo-300/35 bg-indigo-400/5 text-sm text-indigo-200 transition hover:border-indigo-300/70 hover:bg-indigo-400/10">
            <Upload className="size-4" />
            Upload queries.tsv
            <input
              type="file"
              accept=".tsv,text/tab-separated-values,text/plain"
              className="sr-only"
              onChange={async (event) => {
                const input = event.currentTarget
                const file = input.files?.[0]
                if (!file) return
                try {
                  setBatchText((await file.text()).replace(/^\uFEFF/, ""))
                  setBatchError(null)
                } catch {
                  setBatchError("Could not read TSV file.")
                } finally {
                  input.value = ""
                }
              }}
            />
          </label>
          <textarea
            value={batchText}
            onChange={(event) => {
              setBatchText(event.target.value)
              setBatchError(null)
            }}
            onKeyDown={(event) => {
              if (event.key !== "Tab") return
              event.preventDefault()
              const input = event.currentTarget
              input.setRangeText("\t", input.selectionStart, input.selectionEnd, "end")
              setBatchText(input.value)
              setBatchError(null)
            }}
            placeholder={"1\tTübingen attractions\n2\tfood and drinks"}
            spellCheck={false}
            autoFocus
            className="galaxy-scrollbar h-64 w-full resize-none rounded-xl border border-white/10 bg-black/35 p-4 font-mono text-sm leading-6 text-white/85 outline-none transition placeholder:text-white/25 focus:border-indigo-300/50 focus:ring-2 focus:ring-indigo-400/10"
          />
          {batchError && (
            <p className="mt-3 flex items-center gap-2 text-xs text-red-300">
              <CircleAlert className="size-4 shrink-0" />
              {batchError}
            </p>
          )}
          {!batchError && batchText && (
            <p className={`mt-3 text-xs ${batchValidationError ? "text-amber-300" : "text-emerald-300"}`}>
              {batchValidationError || "Valid format"}
            </p>
          )}
          <button
            type="button"
            onClick={() => void downloadBatch()}
            disabled={Boolean(batchValidationError) || batchLoading}
            className="mt-4 flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-indigo-400 font-medium text-[#090a12] transition hover:bg-indigo-300 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {batchLoading ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
            Generate results.tsv
          </button>
        </div>
      </dialog>
    </div>
  )
}

export default App
