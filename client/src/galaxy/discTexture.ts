import { CanvasTexture } from "three"

// soft radial sprite for star points, generated at runtime instead of shipping a texture asset
export function createDiscTexture() {
  const size = 64
  const canvas = document.createElement("canvas")
  canvas.width = canvas.height = size
  const ctx = canvas.getContext("2d")!
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  gradient.addColorStop(0, "rgba(255,255,255,1)")
  gradient.addColorStop(0.4, "rgba(255,255,255,0.6)")
  gradient.addColorStop(1, "rgba(255,255,255,0)")
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, size, size)
  const texture = new CanvasTexture(canvas)
  texture.needsUpdate = true
  return texture
}
