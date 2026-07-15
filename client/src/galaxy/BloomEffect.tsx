import { useEffect, useMemo } from "react"
import { useFrame, useThree } from "@react-three/fiber"
import { EffectComposer, RenderPass, UnrealBloomPass } from "three-stdlib"
import { Vector2 } from "three"

// hand-rolled composer (matches the reference portfolio's approach) instead of
// pulling in @react-three/postprocessing for a single bloom pass
function BloomEffect() {
  const { gl, scene, camera, size } = useThree()

  const composer = useMemo(() => {
    const instance = new EffectComposer(gl)
    instance.addPass(new RenderPass(scene, camera))
    instance.addPass(new UnrealBloomPass(new Vector2(size.width, size.height), 3.6, 1.0, 0.05))
    return instance
  }, [gl, scene, camera])

  useEffect(() => {
    composer.setSize(size.width, size.height)
  }, [composer, size])

  // non-zero priority hands the render loop to us for this frame
  useFrame(() => {
    composer.render()
  }, 1)

  return null
}

export default BloomEffect
