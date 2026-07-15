import { useEffect, useRef } from "react"
import { Canvas, useFrame, useThree } from "@react-three/fiber"
import { PerspectiveCamera, Stars } from "@react-three/drei"
import type { PerspectiveCamera as ThreePerspectiveCamera } from "three"
import gsap from "gsap"

import type { SearchResult } from "@/types"
import GalaxyField from "./GalaxyField"
import WarpTunnel from "./WarpTunnel"
import ResultStars from "./ResultStars"
import BloomEffect from "./BloomEffect"

export type Phase = "idle" | "warping" | "results"

const IDLE_CAMERA = { x: 0, y: 2, z: 11, fov: 45 }
// slight x/y drift while warping so it reads as swooping toward a region of
// the galaxy, not a dead-straight dive through the core
const WARP_CAMERA = { x: 1.6, y: 0.6, z: 1.8, fov: 132 }
const RESULTS_CAMERA = { x: 0, y: 3.5, z: 15, fov: 50 }
// must match MIN_WARP_MS in App.tsx exactly: the tween uses an accelerating
// ease, so if it finishes before results arrive the camera goes dead-still
// at peak speed and holds there — that stop-dead moment is what read as a
// stutter, not a dropped frame
const WARP_DURATION = 1.75

// mirrors the reference portfolio's camera.fov = MathUtils.lerp(...) + updateProjectionMatrix()
// zoom trick, driven by gsap tweens instead of a manual per-frame lerp
function CameraRig({ phase }: { phase: Phase }) {
  const { camera } = useThree() as { camera: ThreePerspectiveCamera }
  const prevPhase = useRef<Phase | null>(null)

  useEffect(() => {
    if (prevPhase.current === phase) return
    prevPhase.current = phase

    const onUpdate = () => camera.updateProjectionMatrix()
    const tl = gsap.timeline()

    if (phase === "warping") {
      // strong ease-in: starts slow, accelerates hard into the galaxy — a launch, not a punch
      tl.to(
        camera.position,
        { x: WARP_CAMERA.x, y: WARP_CAMERA.y, z: WARP_CAMERA.z, duration: WARP_DURATION, ease: "power4.in" },
        0,
      )
      tl.to(camera, { fov: WARP_CAMERA.fov, duration: WARP_DURATION, ease: "power3.in", onUpdate }, 0)
    } else if (phase === "results") {
      // no position.set() snap here on purpose — jumping the camera to a
      // fixed point before tweening created a one-frame gap (galaxy/warp
      // tunnel both just went invisible, stars not grown in yet) that read
      // as a stutter; tweening straight from wherever the warp left off
      // keeps the transition continuous
      tl.to(
        camera.position,
        { x: RESULTS_CAMERA.x, y: RESULTS_CAMERA.y, z: RESULTS_CAMERA.z, duration: 1.1, ease: "power3.out" },
        0,
      )
      tl.to(camera, { fov: RESULTS_CAMERA.fov, duration: 1.1, ease: "power3.out", onUpdate }, 0)
    } else {
      tl.to(
        camera.position,
        { x: IDLE_CAMERA.x, y: IDLE_CAMERA.y, z: IDLE_CAMERA.z, duration: 1, ease: "power2.out" },
        0,
      )
      tl.to(camera, { fov: IDLE_CAMERA.fov, duration: 1, ease: "power2.out", onUpdate }, 0)
    }

    return () => {
      tl.kill()
    }
  }, [phase, camera])

  // the "sun" (query, or galaxy core) always sits at the origin — keep it centered
  useFrame(() => {
    camera.lookAt(0, 0, 0)
  })

  return null
}

type SceneProps = {
  phase: Phase
  results: SearchResult[]
}

function Scene({ phase, results }: SceneProps) {
  return (
    <Canvas dpr={[1, 2]} gl={{ antialias: true }}>
      <color attach="background" args={["#05060d"]} />
      <PerspectiveCamera makeDefault position={[IDLE_CAMERA.x, IDLE_CAMERA.y, IDLE_CAMERA.z]} fov={IDLE_CAMERA.fov} near={0.05} far={200} />
      <CameraRig phase={phase} />
      <ambientLight intensity={0.5} />
      <Stars radius={50} depth={30} count={3800} factor={1.4} saturation={0} fade speed={0.25} />
      <GalaxyField visible={phase !== "results"} warpSpeed={phase === "warping" ? 6 : 1} />
      <WarpTunnel active={phase === "warping"} />
      {results.length > 0 && <ResultStars results={results} revealed={phase === "results"} />}
      <BloomEffect />
    </Canvas>
  )
}

export default Scene
