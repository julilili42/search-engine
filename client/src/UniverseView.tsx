import type { CSSProperties } from "react"

type SearchResult = {
  rank: number
  score: number
  path: string
  url: string | null
  snippet: string
  embedding_score: number | null
}

type UniverseViewProps = {
  query: string
  results: SearchResult[]
}

const SIZE = 640
const CENTER = SIZE / 2
const SUN_RADIUS = 22
const MIN_ORBIT = 70
const MAX_ORBIT = CENTER - 30
const BACKGROUND_STAR_COUNT = 90
const ORBIT_RINGS = [0.33, 0.66]
// golden angle: spreads points around the center without overlapping spokes
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

function relevanceOf(result: SearchResult) {
  return result.embedding_score ?? result.score
}

function normalize(values: number[]) {
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  return (value: number) => (value - min) / span
}

function labelAnchor(angle: number): "start" | "middle" | "end" {
  const cos = Math.cos(angle)
  if (cos > 0.35) return "start"
  if (cos < -0.35) return "end"
  return "middle"
}

function displayHost(result: SearchResult) {
  if (!result.url) return "local file"
  try {
    return new URL(result.url).hostname.replace(/^www\./, "")
  } catch {
    return result.url
  }
}

// real stars follow the same rule: hotter = bluer-white, cooler = orange-red.
// we reuse that scale here so the brightest (most relevant) stars read as "hot".
function starColor(unit: number) {
  const hue = 20 + unit * 200
  const lightness = 65 + unit * 20
  return `hsl(${hue}, 85%, ${lightness}%)`
}

// deterministic pseudo-random in [0, 1), stable across re-renders
function seeded(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

function twinkleStyle(seed: number, baseOpacity: number) {
  const duration = 2 + seeded(seed) * 3
  const delay = seeded(seed + 500) * 4
  return {
    "--twinkle-min": baseOpacity * 0.5,
    "--twinkle-max": baseOpacity,
    animation: `twinkle ${duration}s ease-in-out ${delay}s infinite alternate`,
  } as CSSProperties
}

function appearStyle(rank: number) {
  const delay = 0.15 + seeded(rank * 3.7) * 0.5
  return {
    transformBox: "fill-box",
    transformOrigin: "center",
    animation: `star-appear 0.5s ease-out ${delay}s both`,
  } as CSSProperties
}

function BackgroundStars() {
  const stars = Array.from({ length: BACKGROUND_STAR_COUNT }, (_, i) => {
    const x = seeded(i * 3.1) * SIZE
    const y = seeded(i * 7.7 + 1) * SIZE
    const r = 0.5 + seeded(i * 11.3) * 1
    const opacity = 0.15 + seeded(i * 5.9) * 0.35
    return (
      <circle
        key={i}
        cx={x}
        cy={y}
        r={r}
        fill="white"
        opacity={opacity}
        style={twinkleStyle(i, opacity)}
      />
    )
  })
  return <>{stars}</>
}

function OrbitRings() {
  return (
    <>
      {ORBIT_RINGS.map((fraction) => (
        <circle
          key={fraction}
          cx={CENTER}
          cy={CENTER}
          r={MIN_ORBIT + fraction * (MAX_ORBIT - MIN_ORBIT)}
          fill="none"
          stroke="#94a3b8"
          strokeWidth={0.5}
          strokeDasharray="2 6"
          opacity={0.25}
        />
      ))}
    </>
  )
}

function UniverseView({ query, results }: UniverseViewProps) {
  const withUrl = results.filter((result) => result.url)

  if (withUrl.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No results to place in the universe yet.
      </p>
    )
  }

  const toUnit = normalize(withUrl.map(relevanceOf))
  const placed = withUrl.map((result) => {
    const unit = toUnit(relevanceOf(result))
    const angle = result.rank * GOLDEN_ANGLE
    const orbit = MIN_ORBIT + (1 - unit) * (MAX_ORBIT - MIN_ORBIT)
    return {
      result,
      unit,
      angle,
      x: CENTER + orbit * Math.cos(angle),
      y: CENTER + orbit * Math.sin(angle),
    }
  })

  return (
    <div className="flex flex-col gap-2">
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="w-full rounded-xl border"
        style={{ background: "radial-gradient(circle at center, #0b1020 0%, #05060a 75%)" }}
      >
        <BackgroundStars />
        <OrbitRings />

        {placed.map(({ result, unit, x, y }) => (
          <line
            key={`line-${result.rank}-${result.path}`}
            x1={CENTER}
            y1={CENTER}
            x2={x}
            y2={y}
            stroke="#fef9e7"
            strokeWidth={0.6}
            opacity={0.04 + unit * 0.36}
            style={appearStyle(result.rank)}
          />
        ))}

        {placed.map(({ result, unit, angle, x, y }) => {
          const starRadius = 3 + unit * 7
          const opacity = 0.35 + unit * 0.65
          const color = starColor(unit)
          const twinkle = twinkleStyle(result.rank, opacity)
          const appear = appearStyle(result.rank)
          const labelOffset = starRadius + 10
          const labelX = x + labelOffset * Math.cos(angle)
          const labelY = y + labelOffset * Math.sin(angle)

          return (
            <a
              key={`star-${result.rank}-${result.path}`}
              href={result.url ?? undefined}
              target="_blank"
              rel="noreferrer"
              className="group cursor-pointer"
            >
              <circle
                cx={x}
                cy={y}
                r={starRadius}
                fill={color}
                opacity={opacity}
                style={{
                  ...twinkle,
                  animation: `${appear.animation}, ${twinkle.animation}`,
                  transformBox: "fill-box",
                  transformOrigin: "center",
                  filter: `drop-shadow(0 0 ${4 + unit * 8}px ${color})`,
                }}
              >
                <title>
                  {displayHost(result)} — relevance {unit.toFixed(2)}
                </title>
              </circle>
              <text
                x={labelX}
                y={labelY}
                textAnchor={labelAnchor(angle)}
                dominantBaseline="middle"
                pointerEvents="none"
                className="fill-white text-[10px] opacity-0 transition-opacity duration-150 group-hover:opacity-100"
              >
                {displayHost(result)}
              </text>
            </a>
          )
        })}

        <circle
          cx={CENTER}
          cy={CENTER}
          r={SUN_RADIUS + 10}
          fill="none"
          stroke="#fbbf24"
          strokeWidth={1}
          opacity={0.25}
        />
        <circle
          cx={CENTER}
          cy={CENTER}
          r={SUN_RADIUS}
          fill="#fbbf24"
          className="animate-pulse"
          style={{ filter: "drop-shadow(0 0 18px rgba(251, 191, 36, 0.9))" }}
        />
        <text
          x={CENTER}
          y={CENTER + SUN_RADIUS + 20}
          textAnchor="middle"
          className="fill-white text-[13px]"
        >
          {query}
        </text>
      </svg>
      <p className="text-muted-foreground text-center text-xs">
        Closer, brighter and bluer-white = more relevant, like hotter stars. Hover a star for its source, click to open it.
      </p>
    </div>
  )
}

export default UniverseView
