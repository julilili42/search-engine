import { useEffect, useMemo, useRef, useState } from "react"
import { useFrame } from "@react-three/fiber"
import { Html } from "@react-three/drei"
import { Color, Group, Mesh, MathUtils } from "three"

import type { SearchResult } from "@/types"

type ResultStarsProps = {
  results: SearchResult[]
}

const MIN_ORBIT = 3
const MAX_ORBIT = 9
const AXIS_SPREAD = 7
// golden angle: spreads points around the center without overlapping spokes,
// used as a fallback when embedding coordinates aren't available
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))
// stars this close together are hard to pick apart with the cursor — hovering
// any one of them nudges the whole cluster apart
const CLUSTER_DISTANCE = 1.0
const CLUSTER_SPREAD = 0.45
// grace period before a spread cluster collapses back together, so moving the
// cursor from one just-separated star to its neighbor doesn't snap them shut
// again mid-transit
const UNHOVER_GRACE_MS = 250

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

// stellar classification colors (M -> K -> G -> A -> O/B): red, orange, yellow-white,
// white, blue-white. A plain hue sweep would cross green/cyan, which real stars never do.
const STAR_COLOR_STOPS: [number, string][] = [
  [0, "#ff5a36"],
  [0.35, "#ffab5c"],
  [0.6, "#fff2c2"],
  [0.8, "#ffffff"],
  [1, "#a9c4ff"],
]

function starColor(unit: number) {
  const t = MathUtils.clamp(unit, 0, 1)
  for (let i = 0; i < STAR_COLOR_STOPS.length - 1; i++) {
    const [t0, c0] = STAR_COLOR_STOPS[i]
    const [t1, c1] = STAR_COLOR_STOPS[i + 1]
    if (t <= t1) {
      return new Color(c0).lerp(new Color(c1), (t - t0) / (t1 - t0))
    }
  }
  return new Color(STAR_COLOR_STOPS[STAR_COLOR_STOPS.length - 1][1])
}

// XY only: the depth jitter is a few tenths of a unit purely for visual variety and
// barely moves the on-screen projection at this camera distance, so it shouldn't be
// able to hide an otherwise-overlapping pair from cluster detection
function screenDistance(a: [number, number, number], b: [number, number, number]) {
  return Math.hypot(a[0] - b[0], a[1] - b[1])
}

function layoutStars(results: SearchResult[]) {
  const toUnit = normalize(results.map(relevanceOf))
  const hasEmbeddingCoords = results.every((r) => r.embedding_x !== null && r.embedding_y !== null)

  const placed = results.map((result, index) => {
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

  // stars close enough to be hard to pick apart, keyed by index into `placed`
  const neighbors = placed.map((p, i) =>
    placed.flatMap((q, j) => (i !== j && screenDistance(p.position, q.position) < CLUSTER_DISTANCE ? [j] : [])),
  )

  return placed.map((p, i) => ({ ...p, neighbors: neighbors[i] }))
}

// nudges every member of the active cluster radially away from the cluster's
// centroid, so overlapping stars fan out and become individually clickable
function spreadOffsetFor(
  index: number,
  clusterIndices: number[],
  placed: { position: [number, number, number] }[],
) {
  if (clusterIndices.length < 2) return [0, 0, 0] as [number, number, number]

  const centroid = clusterIndices.reduce(
    (sum, i) => [sum[0] + placed[i].position[0], sum[1] + placed[i].position[1]],
    [0, 0],
  )
  centroid[0] /= clusterIndices.length
  centroid[1] /= clusterIndices.length

  const [px, py] = placed[index].position
  const dx = px - centroid[0]
  const dy = py - centroid[1]
  const len = Math.hypot(dx, dy)
  if (len > 1e-4) {
    return [(dx / len) * CLUSTER_SPREAD, (dy / len) * CLUSTER_SPREAD, 0] as [number, number, number]
  }
  // stars sitting exactly on the centroid (near-identical coords) fan out by angle instead
  const angle = index * GOLDEN_ANGLE
  return [Math.cos(angle) * CLUSTER_SPREAD, Math.sin(angle) * CLUSTER_SPREAD, 0] as [number, number, number]
}

type StarProps = {
  result: SearchResult
  unit: number
  position: [number, number, number]
  spreadOffset: [number, number, number]
  spreading: boolean
  delay: number
  onHoverChange: (hovered: boolean) => void
}

function Star({ result, unit, position, spreadOffset, spreading, delay, onHoverChange }: StarProps) {
  const groupRef = useRef<Group>(null!)
  const meshRef = useRef<Mesh>(null!)
  const [hovered, setHovered] = useState(false)
  const color = useMemo(() => starColor(unit), [unit])
  const size = 0.12 + unit * 0.22
  const seed = useMemo(() => Math.random() * 10, [])
  const mountedAt = useRef<number | null>(null)

  useFrame(({ clock }, delta) => {
    if (mountedAt.current === null) mountedAt.current = clock.getElapsedTime()
    const elapsed = clock.getElapsedTime() - mountedAt.current
    const appear = MathUtils.clamp((elapsed - delay) / 0.6, 0, 1)
    const eased = 1 - Math.pow(1 - appear, 3)
    const twinkle = 1 + Math.sin(elapsed * 2 + seed * 7) * 0.08
    const hoverBoost = hovered ? 1.4 : 1
    meshRef.current.scale.setScalar(eased * twinkle * hoverBoost)

    // ease toward the target position instead of snapping — matters both when
    // the user edits a category axis (reflow) and when a crowded cluster
    // spreads apart on hover
    const target = spreading
      ? [position[0] + spreadOffset[0], position[1] + spreadOffset[1], position[2] + spreadOffset[2]]
      : position
    groupRef.current.position.x = MathUtils.damp(groupRef.current.position.x, target[0], 6, delta)
    groupRef.current.position.y = MathUtils.damp(groupRef.current.position.y, target[1], 6, delta)
    groupRef.current.position.z = MathUtils.damp(groupRef.current.position.z, target[2], 6, delta)
  })

  function openResult() {
    if (result.url) window.open(result.url, "_blank", "noopener,noreferrer")
  }

  function handlePointerOver() {
    setHovered(true)
    onHoverChange(true)
  }

  function handlePointerOut() {
    setHovered(false)
    onHoverChange(false)
  }

  return (
    <group ref={groupRef} position={position}>
      <mesh ref={meshRef} onClick={openResult} onPointerOver={handlePointerOver} onPointerOut={handlePointerOut}>
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

function ResultStars({ results }: ResultStarsProps) {
  const placed = useMemo(() => layoutStars(results), [results])
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null)
  const clearTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (clearTimer.current !== null) clearTimeout(clearTimer.current)
    }
  }, [])

  function handleHoverChange(index: number, hovered: boolean) {
    if (clearTimer.current !== null) {
      clearTimeout(clearTimer.current)
      clearTimer.current = null
    }
    if (hovered) {
      setHoveredIndex(index)
    } else {
      // grace period so the cursor can travel to a just-separated neighbor
      // without the cluster collapsing back together mid-move
      clearTimer.current = setTimeout(() => setHoveredIndex(null), UNHOVER_GRACE_MS)
    }
  }

  const activeCluster = hoveredIndex === null ? [] : [hoveredIndex, ...placed[hoveredIndex].neighbors]

  return (
    <group>
      {placed.map(({ result, unit, position, delay }, index) => (
        <Star
          key={`${result.rank}-${result.path}`}
          result={result}
          unit={unit}
          position={position}
          delay={delay}
          spreading={activeCluster.includes(index)}
          spreadOffset={spreadOffsetFor(index, activeCluster, placed)}
          onHoverChange={(hovered) => handleHoverChange(index, hovered)}
        />
      ))}
    </group>
  )
}

export default ResultStars
