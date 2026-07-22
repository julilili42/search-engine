import { useEffect, useRef, type PointerEvent as ReactPointerEvent, type RefObject } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { PerspectiveCamera, Stars } from "@react-three/drei"
import type { PerspectiveCamera as ThreePerspectiveCamera } from "three"
import gsap from "gsap"

import type { SearchResult } from "@/types"
import GalaxyField from "./GalaxyField"
import WarpTunnel from "./WarpTunnel"
import ResultStars, { PAGE_SPACING } from "./ResultStars"
import BloomEffect from "./BloomEffect"

export type Phase = "idle" | "warping" | "results"

const IDLE_CAMERA = { x: 0, y: 2, z: 11, fov: 45 }
// WARP_CAMERA is also where the camera *stays* for results — there is no
// second leg of travel after the dive. The camera always looks at the
// origin (or the current page's center), so distance-to-target necessarily
// shrinks-then-grows around whatever point the camera stops closest to —
// that's what your eye actually tracks, not the world-space path. Any
// further camera movement after the dive's closest point, in any direction,
// reads as "flying back out" the instant that distance starts growing again.
// The only way to avoid it is to not move the camera again: warp dives
// straight to the point results needs anyway, and the "reveal" is carried
// entirely by FOV (fisheye peak easing back to a normal lens) and the stars
// growing in, not by any further dolly.
const WARP_CAMERA = { x: 0.9, y: 2.8, z: 8, fov: 132 }
// wide enough that every result star sits comfortably inside the frame
// instead of crowding the edges (half-height at z=8 needs to clear the ~7-9
// unit spread the embedding-coordinate layout can produce)
const RESULTS_FOV = 92
// must match MIN_WARP_MS in App.tsx exactly: the tween uses an accelerating
// ease, so if it finishes before results arrive the camera goes dead-still
// at peak speed and holds there — that stop-dead moment is what read as a
// stutter, not a dropped frame
const WARP_DURATION = 1.75

// horizontal drag-to-pan between result pages (in addition to the prev/next
// buttons). World units of camera pan per pixel dragged — deliberately less
// than a full PAGE_SPACING so mid-drag feedback is a preview, not a full
// reveal; the actual page swap (and its own full-distance tween) only
// commits on release, once past DRAG_SNAP_PX.
const DRAG_WORLD_PER_PIXEL = 0.03
const DRAG_SNAP_PX = 120

// mirrors the reference portfolio's camera.fov = MathUtils.lerp(...) + updateProjectionMatrix()
// zoom trick, driven by gsap tweens instead of a manual per-frame lerp
function CameraRig({
  phase,
  page,
  settled,
  lookAt,
  dragOffset,
}: {
  phase: Phase
  page: number
  settled: RefObject<{ x: number; y: number; z: number }>
  lookAt: RefObject<{ x: number }>
  dragOffset: RefObject<{ x: number }>
}) {
  const { camera } = useThree() as { camera: ThreePerspectiveCamera }

  useEffect(() => {
    const onUpdate = () => camera.updateProjectionMatrix()
    const tl = gsap.timeline()
    const pageX = phase === "results" ? page * PAGE_SPACING : 0

    if (phase === "warping") {
      // exponential ease-in: even more front-loaded than the power eases —
      // stays slow/dim noticeably longer, then rockets into the galaxy right
      // at the end, instead of ramping up steadily throughout
      tl.to(
        settled.current,
        { x: WARP_CAMERA.x, y: WARP_CAMERA.y, z: WARP_CAMERA.z, duration: WARP_DURATION, ease: "expo.in" },
        0,
      )
      tl.to(camera, { fov: WARP_CAMERA.fov, duration: WARP_DURATION, ease: "expo.in", onUpdate }, 0)
      tl.to(lookAt.current, { x: 0, duration: WARP_DURATION, ease: "expo.in" }, 0)
    } else if (phase === "results") {
      // x is the only thing that still moves here (by pageX, for
      // pagination) — y/z/fov target the exact same point the warp dive
      // already ended at, so at page 0 this is a zero-distance tween. The
      // "transition to the stars" is FOV alone: it eases from the warp's
      // fisheye peak down to a normal lens while the stars grow in — no
      // camera flight to read as bouncing off anything.
      tl.to(settled.current, { x: WARP_CAMERA.x + pageX, y: WARP_CAMERA.y, z: WARP_CAMERA.z, duration: 1.1, ease: "power2.out" }, 0)
      tl.to(camera, { fov: RESULTS_FOV, duration: 1.1, ease: "power2.out", onUpdate }, 0)
      tl.to(lookAt.current, { x: pageX, duration: 1.1, ease: "power2.out" }, 0)
    } else {
      tl.to(
        settled.current,
        { x: IDLE_CAMERA.x, y: IDLE_CAMERA.y, z: IDLE_CAMERA.z, duration: 1, ease: "power2.out" },
        0,
      )
      tl.to(camera, { fov: IDLE_CAMERA.fov, duration: 1, ease: "power2.out", onUpdate }, 0)
      tl.to(lookAt.current, { x: 0, duration: 1, ease: "power2.out" }, 0)
    }

    return () => {
      tl.kill()
    }
  }, [phase, page, camera])

  useFrame(() => {
    camera.position.set(settled.current.x + dragOffset.current.x, settled.current.y, settled.current.z)
    camera.lookAt(lookAt.current.x + dragOffset.current.x, 0, 0)
  })

  return null
}

type SceneProps = {
  phase: Phase
  results: SearchResult[]
  page: number
  totalPages: number
  onPageDelta: (delta: number) => void
  hasCategoryX: boolean
  hasCategoryY: boolean
}

function Scene({ phase, results, page, totalPages, onPageDelta, hasCategoryX, hasCategoryY }: SceneProps) {
  // settled/lookAt/dragOffset all live here (not inside CameraRig) for two
  // reasons: this is where the DOM pointer props naturally attach to the
  // Canvas element (dragging works from anywhere over the scene, including
  // on top of a star, since stopping propagation on a star's R3F
  // pointerover/out doesn't stop this native DOM listener from also seeing
  // the same pointerdown/move/up) — and because handlePointerUp needs to
  // *write* settled/lookAt directly (see below), not just dragOffset.
  const settled = useRef({ x: IDLE_CAMERA.x, y: IDLE_CAMERA.y, z: IDLE_CAMERA.z })
  const lookAt = useRef({ x: 0 })
  const dragOffset = useRef({ x: 0 })
  const dragStartX = useRef<number | null>(null)

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (phase !== "results") return
    dragStartX.current = event.clientX
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragStartX.current === null) return
    let deltaPx = event.clientX - dragStartX.current
    // clamp the drag preview at the edges: dragging right at page 0 (no
    // previous page) or left at the last page (no next page) should go
    // nowhere instead of previewing a page that doesn't exist
    if (page === 0 && deltaPx > 0) deltaPx = 0
    if (page >= totalPages - 1 && deltaPx < 0) deltaPx = 0
    // dragging left brings the next (rightward, +x) page's cluster into
    // view, like swiping a filmstrip — so the camera pans the opposite way
    // from the drag, toward +x, which is what makes the scene appear to
    // follow the cursor
    dragOffset.current.x = -deltaPx * DRAG_WORLD_PER_PIXEL
  }

  function handlePointerUp(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragStartX.current === null) return
    const deltaPx = event.clientX - dragStartX.current
    dragStartX.current = null

    // fold the live drag preview into settled/lookAt *before* deciding what
    // happens next, so whichever tween runs — a fresh page tween from
    // CameraRig's effect, or the snap-back below — starts from exactly
    // where the camera visually is right now. The previous version instead
    // left dragOffset non-zero and ran a *separate* tween easing it back to
    // 0 in parallel with the page tween; both were driving camera.position.x
    // at once, fighting each other, which is what showed up as a stutter
    // right at the handoff.
    settled.current.x += dragOffset.current.x
    lookAt.current.x += dragOffset.current.x
    dragOffset.current.x = 0

    if (deltaPx <= -DRAG_SNAP_PX) onPageDelta(1)
    else if (deltaPx >= DRAG_SNAP_PX) onPageDelta(-1)
    else {
      // threshold not crossed: page isn't changing, so CameraRig's effect
      // won't re-run on its own — ease back to the current page's resting
      // spot ourselves
      const pageX = page * PAGE_SPACING
      gsap.to(settled.current, { x: WARP_CAMERA.x + pageX, duration: 0.5, ease: "power2.out" })
      gsap.to(lookAt.current, { x: pageX, duration: 0.5, ease: "power2.out" })
    }
  }

  return (
    <Canvas
      dpr={[1, 2]}
      gl={{ antialias: true }}
      style={{ cursor: phase === "results" ? "grab" : "default" }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
    >
      <color attach="background" args={["#05060d"]} />
      <PerspectiveCamera makeDefault position={[IDLE_CAMERA.x, IDLE_CAMERA.y, IDLE_CAMERA.z]} fov={IDLE_CAMERA.fov} near={0.05} far={200} />
      <CameraRig phase={phase} page={page} settled={settled} lookAt={lookAt} dragOffset={dragOffset} />
      <ambientLight intensity={0.5} />
      <Stars radius={50} depth={30} count={3800} factor={1.4} saturation={0} fade speed={0.25} />
      <GalaxyField visible={phase !== "results"} warpSpeed={phase === "warping" ? 6 : 1} />
      <WarpTunnel active={phase === "warping"} />
      {results.length > 0 && (
        <ResultStars
          results={results}
          revealed={phase === "results"}
          hasCategoryX={hasCategoryX}
          hasCategoryY={hasCategoryY}
        />
      )}
      <BloomEffect />
    </Canvas>
  )
}

export default Scene
