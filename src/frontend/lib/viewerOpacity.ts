/**
 * The viewer's opacity slider (0.6.3.0, decision 8.165 C): one value that
 * fades the body of the piece (the mesh with its edges, the proxy, the point
 * cloud) so the overlays inside it show through. Overlays keep their own
 * look: reinforcement bars, test positions, marker points, capture fixtures
 * (0.35 of their own), the grid and the deviation overlay.
 *
 * Loaders cache some objects across viewers, so a viewer never changes a
 * cached material: it takes a copy (`copyForViewer`) and fades the copy.
 *
 * Run: npm test
 */
import * as THREE from 'three'

export const OPACITY_DEFAULT = 100
export const OPACITY_MIN = 0
export const OPACITY_MAX = 100
export const OPACITY_STEP = 5

/** Layers the slider fades (the piece itself). */
export const BODY_LAYERS = ['mesh', 'mesh-edges', 'proxy', 'proxy-edges', 'point-cloud'] as const
/** Layers it never touches (context drawn on or around the piece). */
export const OVERLAY_LAYERS = [
  'reinforcement',
  'test-positions',
  'marker-points',
  'capture-fixtures',
  'proxy-overlay',
  'grid',
] as const

export type BodyLayer = (typeof BODY_LAYERS)[number]
export type OverlayLayer = (typeof OVERLAY_LAYERS)[number]
export type ViewerLayer = BodyLayer | OverlayLayer

export function isBodyLayer(layer: string): layer is BodyLayer {
  return (BODY_LAYERS as readonly string[]).includes(layer)
}

/** What the viewer shows now; the pure input of `visibleBodyLayers`. */
export type LayerState = {
  /** The proxy stands in for the mesh (chosen, or nothing else is stored). */
  showingProxy: boolean
  showProxyMesh: boolean
  showEdges: boolean
  /** Visibility of each mesh (not used while the proxy is shown). */
  visibleMeshes: readonly boolean[]
  visiblePointClouds: readonly boolean[]
}

/** The body layers that are on screen, in drawing order. */
export function visibleBodyLayers(state: LayerState): BodyLayer[] {
  const layers: BodyLayer[] = []
  if (state.showingProxy) {
    if (state.showProxyMesh) layers.push('proxy')
    if (state.showEdges) layers.push('proxy-edges')
  } else if (state.visibleMeshes.some(Boolean)) {
    layers.push('mesh')
    if (state.showEdges) layers.push('mesh-edges')
  }
  if (state.visiblePointClouds.some(Boolean)) layers.push('point-cloud')
  return layers
}

/** A value from the slider or the outside: a whole step, 0..100, else 100. */
export function clampOpacityPercent(value: number): number {
  if (!Number.isFinite(value)) return OPACITY_DEFAULT
  const stepped = Math.round(value / OPACITY_STEP) * OPACITY_STEP
  return Math.min(OPACITY_MAX, Math.max(OPACITY_MIN, stepped))
}

export type MaterialSettings = {
  transparent: boolean
  opacity: number
  depthWrite: boolean
}

/**
 * The three material fields for a percentage. 100 % is the original opaque
 * state exactly (transparent off, depthWrite on), so the default look is
 * unchanged.
 */
export function materialSettings(percent: number): MaterialSettings {
  const value = clampOpacityPercent(percent)
  if (value >= OPACITY_MAX) return { transparent: false, opacity: 1, depthWrite: true }
  return { transparent: true, opacity: value / 100, depthWrite: false }
}

/** Fade one material; every other field (colours, point size, ...) stays. */
export function applyOpacity(material: THREE.Material, percent: number): void {
  const next = materialSettings(percent)
  const flipped = material.transparent !== next.transparent
  material.transparent = next.transparent
  material.opacity = next.opacity
  material.depthWrite = next.depthWrite
  // the shader keeps an opaque variant: a change of the flag needs a rebuild
  if (flipped) material.needsUpdate = true
}

function materialsOf(object: THREE.Object3D): THREE.Material[] {
  const material = (object as THREE.Mesh).material as THREE.Material | THREE.Material[] | undefined
  if (!material) return []
  return Array.isArray(material) ? material : [material]
}

/** Fade every material under `root` (the root included). */
export function applyOpacityToObject(root: THREE.Object3D, percent: number): void {
  root.traverse((object) => {
    for (const material of materialsOf(object)) applyOpacity(material, percent)
  })
}

/**
 * A copy of a (possibly cached) group for one viewer: the same geometry, its
 * own materials. Fading the copy never reaches the original or the copy of
 * another viewer.
 */
export function copyForViewer<T extends THREE.Object3D>(source: T): T {
  const copy = source.clone(true) as T
  copy.traverse((object) => {
    const mesh = object as THREE.Mesh
    if (!mesh.material) return
    mesh.material = Array.isArray(mesh.material)
      ? mesh.material.map((material) => material.clone())
      : mesh.material.clone()
  })
  return copy
}

/** Free the materials of a copy; the geometry belongs to the cache. */
export function disposeViewerCopy(copy: THREE.Object3D): void {
  copy.traverse((object) => {
    for (const material of materialsOf(object)) material.dispose()
  })
}
