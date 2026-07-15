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
const WARP_CAMERA = { z: 2.2, fov: 120 }
const RESULTS_CAMERA = { x: 0, y: 3.5, z: 15, fov: 50 }

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
      tl.to(camera.position, { z: WARP_CAMERA.z, duration: 0.9, ease: "power2.in" }, 0)
      tl.to(camera, { fov: WARP_CAMERA.fov, duration: 0.9, ease: "power2.in", onUpdate }, 0)
    } else if (phase === "results") {
      camera.position.set(0, RESULTS_CAMERA.y, 0.15)
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
  query: string
  results: SearchResult[]
}

function Scene({ phase, query, results }: SceneProps) {
  return (
    <Canvas dpr={[1, 2]} gl={{ antialias: true }}>
      <color attach="background" args={["#05060d"]} />
      <PerspectiveCamera makeDefault position={[IDLE_CAMERA.x, IDLE_CAMERA.y, IDLE_CAMERA.z]} fov={IDLE_CAMERA.fov} near={0.05} far={200} />
      <CameraRig phase={phase} />
      <ambientLight intensity={0.5} />
      <Stars radius={80} depth={50} count={2500} factor={2} fade speed={0.4} />
      <GalaxyField visible={phase !== "results"} warpSpeed={phase === "warping" ? 6 : 1} />
      <WarpTunnel active={phase === "warping"} />
      {phase === "results" && <ResultStars query={query} results={results} />}
      <BloomEffect />
    </Canvas>
  )
}

export default Scene
