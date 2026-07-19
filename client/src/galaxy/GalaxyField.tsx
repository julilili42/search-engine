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

// a second, dimmer, much softer layer over the same spiral: bigger points,
// looser scatter (lower randomness power spreads them off the arms instead of
// hugging them) and a duller brown-violet tint. On its own it's a faint haze;
// under bloom it's what actually reads as light scattering through dust
// instead of just "stars, but blurry".
const DUST_COUNT = 6000
const DUST_RADIUS = 12
const DUST_RANDOMNESS = 0.9
const DUST_RANDOMNESS_POWER = 1.4
const DUST_INSIDE_COLOR = new Color("#3a2a22")
const DUST_OUTSIDE_COLOR = new Color("#241b3d")

function buildDustGeometry() {
  const positions = new Float32Array(DUST_COUNT * 3)
  const colors = new Float32Array(DUST_COUNT * 3)
  const mixed = new Color()

  for (let i = 0; i < DUST_COUNT; i++) {
    const i3 = i * 3
    const radius = Math.random() * DUST_RADIUS
    const branchAngle = ((i % BRANCHES) / BRANCHES) * Math.PI * 2
    const spinAngle = radius * SPIN

    const sign = () => (Math.random() < 0.5 ? 1 : -1)
    const randomX = DUST_RANDOMNESS * sign() * Math.pow(Math.random(), DUST_RANDOMNESS_POWER) * radius
    const randomY = DUST_RANDOMNESS * sign() * Math.pow(Math.random(), DUST_RANDOMNESS_POWER) * radius * 0.35
    const randomZ = DUST_RANDOMNESS * sign() * Math.pow(Math.random(), DUST_RANDOMNESS_POWER) * radius

    const angle = branchAngle + spinAngle
    positions[i3] = Math.cos(angle) * radius + randomX
    positions[i3 + 1] = randomY
    positions[i3 + 2] = Math.sin(angle) * radius + randomZ

    mixed.copy(DUST_INSIDE_COLOR).lerp(DUST_OUTSIDE_COLOR, radius / DUST_RADIUS)
    colors[i3] = mixed.r
    colors[i3 + 1] = mixed.g
    colors[i3 + 2] = mixed.b
  }

  return { positions, colors }
}

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
  const dustMaterialRef = useRef<PointsMaterial>(null!)
  const texture = useMemo(() => createDiscTexture(), [])
  const { positions, colors } = useMemo(() => buildGalaxyGeometry(), [])
  const { positions: dustPositions, colors: dustColors } = useMemo(() => buildDustGeometry(), [])

  useFrame((_, delta) => {
    groupRef.current.rotation.y += delta * BASE_SPIN_SPEED * warpSpeed
    // fading in (idle reveal) stays slow and gentle. Fading out can't use the
    // same damp approach at any rate: BloomEffect runs a near-zero threshold
    // (0.015) at high strength specifically so the dim dust haze blooms too —
    // which means any damped-but-nonzero opacity in between (0.3, 0.05, ...)
    // still blooms into a clearly visible glow for the handful of frames it
    // takes to decay, however fast. So hiding the galaxy has to be an instant
    // cut to exactly 0, not a fast fade.
    if (materialRef.current) {
      materialRef.current.opacity = visible ? MathUtils.damp(materialRef.current.opacity, 0.9, 4, delta) : 0
    }
    if (dustMaterialRef.current) {
      dustMaterialRef.current.opacity = visible ? MathUtils.damp(dustMaterialRef.current.opacity, 0.45, 4, delta) : 0
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
      <points>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[dustPositions, 3]} />
          <bufferAttribute attach="attributes-color" args={[dustColors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          ref={dustMaterialRef}
          size={0.5}
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
