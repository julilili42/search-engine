import { useMemo, useRef } from "react"
import { useFrame } from "@react-three/fiber"
import { LineSegments } from "three"

const STREAK_COUNT = 450
const SPREAD = 14
const DEPTH = 40
const RESET_Z = 4
const RAMP_DURATION = 1.6 // seconds to reach full speed — sells the "accelerating" feel
const MIN_SPEED = 2
const MAX_SPEED = 36
const MIN_STREAK_LENGTH = 0.3
const MAX_STREAK_LENGTH = 2.6

function randomOffset() {
  return (Math.random() - 0.5) * SPREAD
}

function easeInCubic(t: number) {
  return t * t * t
}

type WarpTunnelProps = {
  active: boolean
}

function WarpTunnel({ active }: WarpTunnelProps) {
  const lineRef = useRef<LineSegments>(null!)
  const rampStart = useRef<number | null>(null)

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

  useFrame(({ clock }, delta) => {
    if (!active || !lineRef.current) {
      rampStart.current = null
      return
    }
    if (rampStart.current === null) rampStart.current = clock.getElapsedTime()

    const progress = Math.min((clock.getElapsedTime() - rampStart.current) / RAMP_DURATION, 1)
    const eased = easeInCubic(progress)
    const speed = MIN_SPEED + (MAX_SPEED - MIN_SPEED) * eased
    const streakLength = MIN_STREAK_LENGTH + (MAX_STREAK_LENGTH - MIN_STREAK_LENGTH) * eased

    for (let i = 0; i < STREAK_COUNT; i++) {
      seeds[i * 3 + 2] += delta * speed
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
      positions[i6 + 5] = z - streakLength
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
