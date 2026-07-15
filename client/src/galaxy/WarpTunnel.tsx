import { useMemo, useRef } from "react"
import { useFrame } from "@react-three/fiber"
import { LineSegments } from "three"

const STREAK_COUNT = 450
const SPREAD = 14
const DEPTH = 40
const STREAK_LENGTH = 1.4
const SPEED = 22
const RESET_Z = 4

function randomOffset() {
  return (Math.random() - 0.5) * SPREAD
}

type WarpTunnelProps = {
  active: boolean
}

function WarpTunnel({ active }: WarpTunnelProps) {
  const lineRef = useRef<LineSegments>(null!)

  const { positions, seeds } = useMemo(() => {
    const positions = new Float32Array(STREAK_COUNT * 2 * 3)
    const seeds = new Float32Array(STREAK_COUNT * 3) // x, y, z per streak
    for (let i = 0; i < STREAK_COUNT; i++) {
      seeds[i * 3] = randomOffset()
      seeds[i * 3 + 1] = randomOffset()
      seeds[i * 3 + 2] = -Math.random() * DEPTH
    }
    return { positions, seeds }
  }, [])

  useFrame((_, delta) => {
    if (!active || !lineRef.current) return

    for (let i = 0; i < STREAK_COUNT; i++) {
      seeds[i * 3 + 2] += delta * SPEED
      if (seeds[i * 3 + 2] > RESET_Z) {
        seeds[i * 3] = randomOffset()
        seeds[i * 3 + 1] = randomOffset()
        seeds[i * 3 + 2] = -DEPTH
      }
      const x = seeds[i * 3]
      const y = seeds[i * 3 + 1]
      const z = seeds[i * 3 + 2]
      const i6 = i * 6
      positions[i6] = x
      positions[i6 + 1] = y
      positions[i6 + 2] = z
      positions[i6 + 3] = x
      positions[i6 + 4] = y
      positions[i6 + 5] = z - STREAK_LENGTH
    }
    lineRef.current.geometry.attributes.position.needsUpdate = true
  })

  return (
    <lineSegments ref={lineRef} visible={active}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <lineBasicMaterial color="#bcd4ff" transparent opacity={0.65} />
    </lineSegments>
  )
}

export default WarpTunnel
