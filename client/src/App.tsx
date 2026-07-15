import { useState, type FormEvent } from "react"
import { Search, Loader2, ExternalLink, Sparkles, CircleAlert, SearchX } from "lucide-react"

import Scene, { type Phase } from "@/galaxy/Scene"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { SearchResult } from "@/types"

const MIN_WARP_MS = 1300
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

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    const q = query.trim()
    if (!q || loading) return

    setPhase("warping")
    setLoading(true)
    setError(null)

    const start = Date.now()
    try {
      const res = await fetch(`/search?q=${encodeURIComponent(q)}&top_n=10`)
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
                className="block rounded-lg border border-white/10 bg-white/5 px-3 py-2 transition-colors hover:bg-white/10"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="flex min-w-0 items-center gap-1.5 truncate text-sm font-medium">
                    <span className="text-white/40">{result.rank}.</span>
                    {displayHost(result)}
                  </span>
                  <ExternalLink className="size-3 shrink-0 text-white/40" />
                </div>
                <p className="mt-0.5 line-clamp-1 text-xs text-white/50">{result.snippet}</p>
              </a>
            ))}
        </div>
      </aside>

      <main className="relative flex-1">
        <Scene phase={phase} query={query} results={results} />
      </main>
    </div>
  )
}

export default App
