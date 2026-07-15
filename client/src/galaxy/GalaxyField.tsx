import { useMemo, useRef } from "react"
import { useFrame } from "@react-three/fiber"
import { AdditiveBlending, Color, Group, MathUtils, PointsMaterial } from "three"

import { createDiscTexture } from "./discTexture"

const COUNT = 12000
const RADIUS = 9
const BRANCHES = 4
const SPIN = 1.3
const RANDOMNESS = 0.4
const RANDOMNESS_POWER = 3
const BASE_SPIN_SPEED = 0.025
const INSIDE_COLOR = new Color("#ffcf8a")
const OUTSIDE_COLOR = new Color("#4d6bff")

function buildGalaxyGeometry() {
  const positions = new Float32Array(COUNT * 3)
  const colors = new Float32Array(COUNT * 3)
  const mixed = new Color()

  for (let i = 0; i < COUNT; i++) {
    const i3 = i * 3
    const radius = Math.random() * RADIUS
    const branchAngle = ((i % BRANCHES) / BRANCHES) * Math.PI * 2
    const spinAngle = radius * SPIN

    const sign = () => (Math.random() < 0.5 ? 1 : -1)
    const randomX = RANDOMNESS * sign() * Math.pow(Math.random(), RANDOMNESS_POWER) * radius
    const randomY = RANDOMNESS * sign() * Math.pow(Math.random(), RANDOMNESS_POWER) * radius * 0.3
    const randomZ = RANDOMNESS * sign() * Math.pow(Math.random(), RANDOMNESS_POWER) * radius

    const angle = branchAngle + spinAngle
    positions[i3] = Math.cos(angle) * radius + randomX
    positions[i3 + 1] = randomY
    positions[i3 + 2] = Math.sin(angle) * radius + randomZ

    mixed.copy(INSIDE_COLOR).lerp(OUTSIDE_COLOR, radius / RADIUS)
    colors[i3] = mixed.r
    colors[i3 + 1] = mixed.g
    colors[i3 + 2] = mixed.b
  }

  return { positions, colors }
}

type GalaxyFieldProps = {
  visible: boolean
  warpSpeed: number // 1 = idle drift, higher while warping
}

function GalaxyField({ visible, warpSpeed }: GalaxyFieldProps) {
  const groupRef = useRef<Group>(null!)
  const materialRef = useRef<PointsMaterial>(null!)
  const texture = useMemo(() => createDiscTexture(), [])
  const { positions, colors } = useMemo(() => buildGalaxyGeometry(), [])

  useFrame((_, delta) => {
    groupRef.current.rotation.y += delta * BASE_SPIN_SPEED * warpSpeed
    if (materialRef.current) {
      materialRef.current.opacity = MathUtils.damp(materialRef.current.opacity, visible ? 0.9 : 0, 4, delta)
    }
  })

  return (
    <group ref={groupRef} rotation={[0.15, 0, 0.05]}>
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="attributes-color" args={[colors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          ref={materialRef}
          size={0.065}
          map={texture}
          vertexColors
          transparent
          opacity={0}
          depthWrite={false}
          sizeAttenuation
          blending={AdditiveBlending}
        />
      </points>
    </group>
  )
}

export default GalaxyField
