import { useEffect, useMemo, useRef, useState } from "react"
import { useFrame, type ThreeEvent } from "@react-three/fiber"
import { Html } from "@react-three/drei"
import { Color, Group, Mesh, MathUtils } from "three"

import type { SearchResult } from "@/types"

type ResultStarsProps = {
  results: SearchResult[]
  revealed: boolean
  hasCategoryX: boolean
  hasCategoryY: boolean
}

const AXIS_SPREAD = 7
const RANK_X_SPREAD = 4
const RANK_SPREAD = 6
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))
// distance below which two stars are considered visually overlapping and
// therefore clustered together (kept separate from HOVER_RADIUS below — see
// that constant for why they can't share a value)
const OVERLAP_DISTANCE = 1.0
const CLUSTER_SPREAD = 0.45
// each star's invisible hit-sphere radius, deliberately >> CLUSTER_SPREAD.
// When a cluster spreads, every member moves CLUSTER_SPREAD away from the
// shared centroid, so two spread stars end up ~2 * CLUSTER_SPREAD apart. For
// the cursor to stay "inside the radius" anywhere in the gap between them —
// including the dead centroid point, where a naive radius barely bigger than
// CLUSTER_SPREAD leaves only a hair of overlap — the two hit-spheres need to
// overlap by a comfortable margin, not just touch. HOVER_RADIUS must NOT be
// derived from OVERLAP_DISTANCE (that would just re-couple the two and force
// a choice between "clusters trigger too eagerly" and "hover keeps dropping
// in the gap"); it's sized purely around CLUSTER_SPREAD instead.
const HOVER_RADIUS = 0.9
// lower = slower, smoother easing toward the spread/collapsed position (see MathUtils.damp)
const SPREAD_DAMP = 4
// grace period before a spread cluster collapses back together, so moving the
// cursor from one just-separated star to its neighbor (or through the gap
// between them) doesn't snap them shut again mid-transit
const UNHOVER_GRACE_MS = 450

// results are paged 10-at-a-time; each page gets its own constellation
// cluster offset along x, so paginating is a camera pan to the next cluster
// instead of a re-layout
export const PAGE_SIZE = 10
export const PAGE_SPACING = 24

function relevanceOf(result: SearchResult) {
  return result.score
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

function layoutStars(results: SearchResult[], hasCategoryX: boolean, hasCategoryY: boolean) {
  const toUnit = normalize(results.map(relevanceOf))

  const placed = results.map((result, index) => {
    const unit = toUnit(relevanceOf(result))
    const pageX = Math.floor(index / PAGE_SIZE) * PAGE_SPACING
    const pageLocalIndex = index % PAGE_SIZE
    const rankY = PAGE_SIZE > 1 ? 1 - (2 * pageLocalIndex) / (PAGE_SIZE - 1) : 0
    // Without a category, the ranking itself defines the map: high ranks sit
    // at the top and deterministic X offsets keep them visibly separate.
    const x = pageX + (
      hasCategoryX && Number.isFinite(result.embedding_x)
        ? result.embedding_x! * AXIS_SPREAD
        : seeded(index) * RANK_X_SPREAD
    )
    const y = hasCategoryY && Number.isFinite(result.embedding_y)
      ? result.embedding_y! * AXIS_SPREAD
      : rankY * RANK_SPREAD
    // slight deterministic depth jitter so the constellation isn't a perfectly flat card
    const z = seeded(index * 3.1) * 0.8

    return {
      result,
      unit,
      position: [x, y, z] as [number, number, number],
      delay: 0.1 + pageLocalIndex * 0.08,
    }
  })

  // union-find over `placed` indices, seeded from raw layout overlap (pages
  // sit PAGE_SPACING apart, far past OVERLAP_DISTANCE, so clustering never
  // crosses pages)
  const parent = placed.map((_, i) => i)
  function find(i: number): number {
    while (parent[i] !== i) {
      parent[i] = parent[parent[i]]
      i = parent[i]
    }
    return i
  }
  function union(a: number, b: number) {
    const ra = find(a)
    const rb = find(b)
    if (ra !== rb) parent[ra] = rb
  }

  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      if (screenDistance(placed[i].position, placed[j].position) < OVERLAP_DISTANCE) union(i, j)
    }
  }

  // a cluster fanning out (spreadOffsetFor) can carry one of its members into
  // range of a star that wasn't part of the original overlap — pull that star
  // into the cluster too (so it also fans away) and repeat, since absorbing it
  // can in turn bring in another, until a pass produces no new merges
  for (let pass = 0; pass < 5; pass++) {
    const groups = new Map<number, number[]>()
    for (let i = 0; i < placed.length; i++) {
      const root = find(i)
      const members = groups.get(root) ?? []
      members.push(i)
      groups.set(root, members)
    }
    const spread = placed.map((p, i) => {
      const offset = spreadOffsetFor(i, groups.get(find(i))!, placed)
      return [p.position[0] + offset[0], p.position[1] + offset[1], p.position[2] + offset[2]] as [
        number,
        number,
        number,
      ]
    })

    let merged = false
    for (let i = 0; i < placed.length; i++) {
      for (let j = i + 1; j < placed.length; j++) {
        if (find(i) === find(j)) continue
        if (screenDistance(spread[i], spread[j]) < OVERLAP_DISTANCE) {
          union(i, j)
          merged = true
        }
      }
    }
    if (!merged) break
  }

  const neighbors = placed.map((_, i) => {
    const root = find(i)
    return placed.flatMap((_, j) => (j !== i && find(j) === root ? [j] : []))
  })

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
  revealed: boolean
  onHoverChange: (hovered: boolean) => void
}

function Star({ result, unit, position, spreadOffset, spreading, delay, revealed, onHoverChange }: StarProps) {
  const groupRef = useRef<Group>(null!)
  const initialPosition = useRef(position)
  const meshRef = useRef<Mesh>(null!)
  const [hovered, setHovered] = useState(false)
  const color = useMemo(() => starColor(unit), [unit])
  const size = 0.12 + unit * 0.22
  const seed = useMemo(() => Math.random() * 10, [])
  const mountedAt = useRef<number | null>(null)

  useFrame(({ clock }, delta) => {
    // mounted early (while still warping) so the mesh's GPU buffers/shader
    // get compiled ahead of the reveal instead of at it — kept at scale 0
    // and the appear timer held off until the phase actually flips
    if (!revealed) {
      meshRef.current.scale.setScalar(0)
      mountedAt.current = null
      return
    }
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
    groupRef.current.position.x = MathUtils.damp(groupRef.current.position.x, target[0], SPREAD_DAMP, delta)
    groupRef.current.position.y = MathUtils.damp(groupRef.current.position.y, target[1], SPREAD_DAMP, delta)
    groupRef.current.position.z = MathUtils.damp(groupRef.current.position.z, target[2], SPREAD_DAMP, delta)
  })

  function openResult() {
    if (result.url) window.open(result.url, "_blank", "noopener,noreferrer")
  }

  // stopPropagation is load-bearing: HOVER_RADIUS is now big enough that
  // neighboring stars' hit-spheres genuinely overlap in 3D, so a single ray
  // can intersect more than one of them at once. Without stopping it here,
  // the event keeps propagating to every farther hit-sphere along that same
  // ray, firing pointerOver on all of them — which showed up as two
  // simultaneous tooltips on overlapping stars.
  function handlePointerOver(event: ThreeEvent<PointerEvent>) {
    event.stopPropagation()
    setHovered(true)
    onHoverChange(true)
  }

  function handlePointerOut(event: ThreeEvent<PointerEvent>) {
    event.stopPropagation()
    setHovered(false)
    onHoverChange(false)
  }

  return (
    <group ref={groupRef} position={initialPosition.current}>
      {/* invisible hit-sphere, bigger than the visible dot — this is the actual
          "radius" used for both hover and cluster-overlap detection, so the
          cursor stays "in" a spread cluster even in the gaps between the now
          separated visible dots. visible={revealed} keeps it un-raycastable
          (three.js skips invisible objects) before the reveal, matching the
          scale-0 visible mesh. */}
      <mesh
        visible={revealed}
        onClick={openResult}
        onPointerOver={handlePointerOver}
        onPointerOut={handlePointerOut}
      >
        <sphereGeometry args={[HOVER_RADIUS, 12, 12]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      <mesh ref={meshRef}>
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

// full connected component reachable from `start` via overlapping-radius edges,
// not just its direct neighbors — so a chain of 3+ overlapping stars all
// spread apart together, from whichever one of them is hovered
function clusterOf(start: number, placed: { neighbors: number[] }[]) {
  const seen = new Set([start])
  const stack = [start]
  while (stack.length > 0) {
    const current = stack.pop()!
    for (const neighbor of placed[current].neighbors) {
      if (!seen.has(neighbor)) {
        seen.add(neighbor)
        stack.push(neighbor)
      }
    }
  }
  return [...seen]
}

function ResultStars({ results, revealed, hasCategoryX, hasCategoryY }: ResultStarsProps) {
  const placed = useMemo(
    () => layoutStars(results, hasCategoryX, hasCategoryY),
    [results, hasCategoryX, hasCategoryY],
  )
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

  const activeCluster = hoveredIndex === null ? [] : clusterOf(hoveredIndex, placed)

  return (
    <group>
      {placed.map(({ result, unit, position, delay }, index) => (
        <Star
          key={`${result.rank}-${result.path}`}
          result={result}
          unit={unit}
          position={position}
          delay={delay}
          revealed={revealed}
          spreading={activeCluster.includes(index)}
          spreadOffset={spreadOffsetFor(index, activeCluster, placed)}
          onHoverChange={(hovered) => handleHoverChange(index, hovered)}
        />
      ))}
    </group>
  )
}

export default ResultStars
