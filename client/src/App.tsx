import { useState, type FormEvent } from "react"
import { Search, Loader2, ExternalLink } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card"

type SearchResult = {
  rank: number
  score: number
  path: string
  url: string | null
  snippet: string
}

function App() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState(false)

  async function handleSearch(event: FormEvent) {
    event.preventDefault()
    const q = query.trim()
    if (!q) return

    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`/search?q=${encodeURIComponent(q)}&top_n=10`)
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
    <div className="mx-auto flex min-h-svh max-w-3xl flex-col gap-6 px-4 py-10">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">
          Tübingen Search
        </h1>
        <p className="text-muted-foreground text-sm">
          Searches the local index via the <code>/search</code> endpoint.
        </p>
      </header>

      <form onSubmit={handleSearch} className="flex gap-2">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search term"
          autoFocus
        />
        <Button type="submit" disabled={loading || !query.trim()}>
          {loading ? (
            <Loader2 className="animate-spin" />
          ) : (
            <Search />
          )}
          Search
        </Button>
      </form>

      {error && (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      )}

      {searched && !loading && !error && results.length === 0 && (
        <p className="text-muted-foreground text-sm">No results.</p>
      )}

      <div className="flex flex-col gap-3">
        {results.map((result) => (
          <Card key={`${result.rank}-${result.path}`}>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2">
                <span className="truncate">
                  {result.rank}.{" "}
                  {result.url ? (
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noreferrer"
                      className="hover:underline"
                    >
                      {result.url}
                    </a>
                  ) : (
                    result.path
                  )}
                </span>
                <span className="text-muted-foreground shrink-0 text-xs font-normal">
                  score {result.score.toFixed(3)}
                </span>
              </CardTitle>
              {result.url && (
                <CardDescription className="flex items-center gap-1 truncate">
                  <ExternalLink className="size-3 shrink-0" />
                  {result.path}
                </CardDescription>
              )}
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed">{result.snippet}</p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  )
}

export default App
