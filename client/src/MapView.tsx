import { useEffect, useState, type FormEvent } from "react"
import { Loader2, Map } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

type MapPoint = {
  url: string
  title: string | null
  x: number
  y: number
}

const PRESETS: [string, string][] = [
  ["food", "nature"],
  ["university", "tourism"],
  ["history", "events"],
]

const SIZE = 600
const PAD = 24

function makeScale(values: number[]) {
  const min = Math.min(...values)
  const span = Math.max(...values) - min || 1
  return (value: number) => PAD + ((value - min) / span) * (SIZE - 2 * PAD)
}

function MapView() {
  const [xCat, setXCat] = useState(PRESETS[0][0])
  const [yCat, setYCat] = useState(PRESETS[0][1])
  const [axes, setAxes] = useState(PRESETS[0])
  const [points, setPoints] = useState<MapPoint[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load(x: string, y: string) {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(
        `/map?x=${encodeURIComponent(x)}&y=${encodeURIComponent(y)}`
      )
      if (!res.ok) {
        throw new Error(`Map fehlgeschlagen (HTTP ${res.status})`)
      }
      setPoints(await res.json())
      setAxes([x, y])
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unbekannter Fehler")
      setPoints([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(PRESETS[0][0], PRESETS[0][1])
  }, [])

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (xCat.trim() && yCat.trim()) load(xCat.trim(), yCat.trim())
  }

  function applyPreset([x, y]: [string, string]) {
    setXCat(x)
    setYCat(y)
    load(x, y)
  }

  const scaleX = makeScale(points.map((p) => p.x))
  const scaleY = makeScale(points.map((p) => p.y))

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <Input
          value={xCat}
          onChange={(e) => setXCat(e.target.value)}
          placeholder="X axis, e.g. food"
        />
        <Input
          value={yCat}
          onChange={(e) => setYCat(e.target.value)}
          placeholder="Y axis, e.g. nature"
        />
        <Button type="submit" disabled={loading || !xCat.trim() || !yCat.trim()}>
          {loading ? <Loader2 className="animate-spin" /> : <Map />}
          Map
        </Button>
      </form>

      <div className="flex gap-2">
        {PRESETS.map((preset) => (
          <Button
            key={preset.join("-")}
            variant="secondary"
            size="sm"
            disabled={loading}
            onClick={() => applyPreset(preset)}
          >
            {preset[0]} × {preset[1]}
          </Button>
        ))}
      </div>

      {error && (
        <p className="text-destructive text-sm" role="alert">
          {error}
        </p>
      )}

      {points.length > 0 && (
        <svg
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          className="bg-card w-full rounded-xl border"
        >
          {points.map((point) => (
            <a key={point.url} href={point.url} target="_blank" rel="noreferrer">
              <circle
                cx={scaleX(point.x)}
                cy={SIZE - scaleY(point.y)}
                r={3}
                className="fill-primary/30 hover:fill-primary"
              >
                <title>{point.title ?? point.url}</title>
              </circle>
            </a>
          ))}
          <text
            x={SIZE - PAD}
            y={SIZE - 8}
            textAnchor="end"
            className="fill-muted-foreground text-[11px]"
          >
            {axes[0]} →
          </text>
          <text
            x={8}
            y={PAD}
            textAnchor="end"
            transform={`rotate(-90 8 ${PAD})`}
            className="fill-muted-foreground text-[11px]"
          >
            {axes[1]} →
          </text>
        </svg>
      )}
    </div>
  )
}

export default MapView
