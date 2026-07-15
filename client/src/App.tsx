import { useState, type FormEvent } from "react"
import {
  Search,
  Loader2,
  ExternalLink,
  Orbit,
  List,
  MapPin,
  CircleAlert,
  SearchX,
} from "lucide-react"

import UniverseView from "@/UniverseView"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

type SearchResult = {
  rank: number
  score: number
  path: string
  url: string | null
  snippet: string
  embedding_score: number | null
}

function displayUrl(result: SearchResult) {
  return result.url ?? result.path
}

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
  const [showUniverse, setShowUniverse] = useState(false)

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    const q = query.trim()
    if (!q) return

    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/search?q=${encodeURIComponent(q)}&top_n=30`)
      if (!res.ok) {
        throw new Error(`Suche fehlgeschlagen (HTTP ${res.status})`)
      }
      const data: SearchResult[] = await res.json()
      setResults(data)
      setSearched(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler")
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="from-muted/40 via-background to-background min-h-svh bg-gradient-to-b">
      <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-12">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="bg-primary text-primary-foreground flex size-10 shrink-0 items-center justify-center rounded-xl">
              <MapPin className="size-5" />
            </div>
            <div>
              <h1 className="text-xl leading-tight font-semibold tracking-tight">
                Tübingen Search
              </h1>
              <p className="text-muted-foreground text-xs">
                Local index · BM25F + semantic re-ranking
              </p>
            </div>
          </div>

          <div className="bg-muted flex shrink-0 items-center gap-1 rounded-full p-1">
            <Button
              type="button"
              variant={showUniverse ? "ghost" : "default"}
              size="sm"
              className="rounded-full"
              onClick={() => setShowUniverse(false)}
            >
              <List />
              List
            </Button>
            <Button
              type="button"
              variant={showUniverse ? "default" : "ghost"}
              size="sm"
              className="rounded-full"
              onClick={() => setShowUniverse(true)}
            >
              <Orbit />
              Universe
            </Button>
          </div>
        </header>

        <form onSubmit={handleSearch} className="relative">
          <Search className="text-muted-foreground pointer-events-none absolute top-1/2 left-4 size-4 -translate-y-1/2" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Tübingen..."
            autoFocus
            className="h-12 rounded-full pr-32 pl-11 text-base shadow-sm"
          />
          <Button
            type="submit"
            disabled={loading || !query.trim()}
            className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded-full"
          >
            {loading ? <Loader2 className="animate-spin" /> : <Search />}
            Search
          </Button>
        </form>

        {error && (
          <div className="border-destructive/30 bg-destructive/5 text-destructive flex items-center gap-2 rounded-lg border px-4 py-3 text-sm">
            <CircleAlert className="size-4 shrink-0" />
            {error}
          </div>
        )}

        {searched && !loading && !error && results.length === 0 && (
          <div className="text-muted-foreground flex flex-col items-center gap-2 py-16 text-center">
            <SearchX className="size-8" />
            <p className="text-sm">No results found.</p>
          </div>
        )}

        {searched && results.length > 0 && showUniverse && (
          <UniverseView query={query} results={results} />
        )}

        {(!showUniverse || !searched) && (
          <div className="flex flex-col gap-3">
            {results.map((result, index) => (
              <Card
                key={`${result.rank}-${result.path}`}
                className={cn(
                  "ring-border/60 flex-row items-start gap-4 rounded-2xl border-transparent p-4 shadow-sm ring-1 transition-shadow hover:shadow-md",
                  index === 0 && "ring-primary/40 ring-2",
                )}
              >
                <span className="bg-muted text-muted-foreground mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold">
                  {result.rank}
                </span>
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate font-medium">
                      {displayHost(result)}
                    </span>
                    <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                      {result.score.toFixed(3)}
                    </span>
                  </div>
                  <div className="text-muted-foreground flex min-w-0 items-center gap-1 text-xs">
                    <ExternalLink className="size-3 shrink-0" />
                    {result.url ? (
                      <a
                        href={result.url}
                        target="_blank"
                        rel="noreferrer"
                        className="min-w-0 truncate hover:underline"
                      >
                        {displayUrl(result)}
                      </a>
                    ) : (
                      <span className="min-w-0 truncate">{displayUrl(result)}</span>
                    )}
                  </div>
                  <p className="text-foreground/80 text-sm leading-relaxed">
                    {result.snippet}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default App
