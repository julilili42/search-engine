import { useMemo, useRef, useState } from "react"
import { useFrame } from "@react-three/fiber"
import { Html, Line } from "@react-three/drei"
import { Color, Mesh, MathUtils } from "three"

import type { SearchResult } from "@/types"

type ResultStarsProps = {
  query: string
  results: SearchResult[]
}

const MIN_ORBIT = 3
const MAX_ORBIT = 9
const AXIS_SPREAD = 7
// golden angle: spreads points around the center without overlapping spokes,
// used as a fallback when embedding coordinates aren't available
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

// deterministic pseudo-random in [-1, 1], stable across re-renders
function seeded(seed: number) {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return (x - Math.floor(x)) * 2 - 1
}

function displayHost(result: SearchResult) {
  if (!result.url) return "local file"
  try {
    return new URL(result.url).hostname.replace(/^www\./, "")
  } catch {
    return result.url
  }
}

// real stars follow the same rule: hotter = bluer-white, cooler = orange-red
function starColor(unit: number) {
  const hue = 20 + unit * 200
  const lightness = 55 + unit * 25
  return new Color(`hsl(${hue}, 85%, ${lightness}%)`)
}

function layoutStars(results: SearchResult[]) {
  const toUnit = normalize(results.map(relevanceOf))
  const hasEmbeddingCoords = results.every((r) => r.embedding_x !== null && r.embedding_y !== null)

  return results.map((result, index) => {
    const unit = toUnit(relevanceOf(result))

    // the constellation shape is the two named category axes (embedding_x/y);
    // relevance only drives size/brightness, not placement, so the axes stay legible
    let x: number
    let y: number
    if (hasEmbeddingCoords) {
      x = result.embedding_x! * AXIS_SPREAD
      y = result.embedding_y! * AXIS_SPREAD
    } else {
      const angle = index * GOLDEN_ANGLE
      const orbit = MIN_ORBIT + (1 - unit) * (MAX_ORBIT - MIN_ORBIT)
      x = Math.cos(angle) * orbit
      y = Math.sin(angle) * orbit
    }
    // slight deterministic depth jitter so the constellation isn't a perfectly flat card
    const z = seeded(index * 3.1) * 0.8

    return {
      result,
      unit,
      position: [x, y, z] as [number, number, number],
      delay: 0.1 + index * 0.08,
    }
  })
}

type StarProps = {
  result: SearchResult
  unit: number
  position: [number, number, number]
  delay: number
}

function Star({ result, unit, position, delay }: StarProps) {
  const meshRef = useRef<Mesh>(null!)
  const [hovered, setHovered] = useState(false)
  const color = useMemo(() => starColor(unit), [unit])
  const size = 0.12 + unit * 0.22
  const seed = useMemo(() => Math.random() * 10, [])
  const mountedAt = useRef<number | null>(null)

  useFrame(({ clock }) => {
    if (mountedAt.current === null) mountedAt.current = clock.getElapsedTime()
    const elapsed = clock.getElapsedTime() - mountedAt.current
    const appear = MathUtils.clamp((elapsed - delay) / 0.6, 0, 1)
    const eased = 1 - Math.pow(1 - appear, 3)
    const twinkle = 1 + Math.sin(elapsed * 2 + seed * 7) * 0.08
    const hoverBoost = hovered ? 1.4 : 1
    meshRef.current.scale.setScalar(eased * twinkle * hoverBoost)
  })

  function openResult() {
    if (result.url) window.open(result.url, "_blank", "noopener,noreferrer")
  }

  return (
    <group position={position}>
      <Line points={[[0, 0, 0], [-position[0], -position[1], -position[2]]]} color="#fef9e7" opacity={0.05 + unit * 0.3} transparent lineWidth={1} />
      <mesh
        ref={meshRef}
        onClick={openResult}
        onPointerOver={() => setHovered(true)}
        onPointerOut={() => setHovered(false)}
      >
        <sphereGeometry args={[size, 16, 16]} />
        <meshBasicMaterial color={color} toneMapped={false} />
      </mesh>
      {hovered && (
        <Html distanceFactor={10} style={{ pointerEvents: "none" }}>
          <div className="rounded-md bg-black/80 px-2 py-1 text-xs whitespace-nowrap text-white shadow-lg">
            {displayHost(result)}
          </div>
        </Html>
      )}
    </group>
  )
}

function ResultStars({ query, results }: ResultStarsProps) {
  const placed = useMemo(() => layoutStars(results), [results])

  return (
    <group>
      <mesh>
        <sphereGeometry args={[0.5, 24, 24]} />
        <meshBasicMaterial color="#fbbf24" toneMapped={false} />
      </mesh>
      <Html distanceFactor={10} position={[0, -0.9, 0]} style={{ pointerEvents: "none" }}>
        <div className="text-sm font-medium whitespace-nowrap text-white/90">{query}</div>
      </Html>

      {placed.map(({ result, unit, position, delay }) => (
        <Star key={`${result.rank}-${result.path}`} result={result} unit={unit} position={position} delay={delay} />
      ))}
    </group>
  )
}

export default ResultStars
