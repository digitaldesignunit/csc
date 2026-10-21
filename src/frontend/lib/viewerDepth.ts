/**
 * Faces sit a hair behind their edges (0.6.3.1): a mesh and the lines of its
 * edges lie in the same surface, so at some angles the depth test let the
 * faces cut the lines. The face materials carry a polygon offset, which moves
 * the faces a little back in depth while the edges stay where they are. The
 * depth test of the edges stays on: back edges are hidden by the faces as
 * before, only the edges of the visible side win.
 *
 * Run: npm test
 */
import * as THREE from 'three'

/** Offset of the faces: the slope factor handles steep faces, the units the flat ones. */
export const FACE_POLYGON_OFFSET = {
  polygonOffset: true,
  polygonOffsetFactor: 1,
  polygonOffsetUnits: 1,
} as const

/** Move the faces of a material back (an existing one, e.g. a built-in mesh). */
export function pushFacesBack<T extends THREE.Material>(material: T): T {
  material.polygonOffset = FACE_POLYGON_OFFSET.polygonOffset
  material.polygonOffsetFactor = FACE_POLYGON_OFFSET.polygonOffsetFactor
  material.polygonOffsetUnits = FACE_POLYGON_OFFSET.polygonOffsetUnits
  return material
}

/** The material of the faces of a mesh: vertex colours or grey, both sides, faces set back. */
export function bodyFaceMaterial(hasColors: boolean): THREE.MeshBasicMaterial {
  return pushFacesBack(hasColors
    ? new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })
    : new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.DoubleSide }))
}

/** The material of the edge lines: black, depth test on, no offset. */
export function edgeLineMaterial(): THREE.LineBasicMaterial {
  return new THREE.LineBasicMaterial({ color: 0x000000 })
}

/** The camera planes (near, far) in the units of the scene. */
export type DepthRange = { near: number; far: number }

/** Nearest the near plane may come, as a share of the piece's radius. */
export const NEAR_FLOOR = 1e-4

/**
 * The camera's near and far planes (0.6.3.1). They follow the camera, not the
 * first fit: ``distance`` is the distance of the camera to its orbit target
 * (the middle of the piece) and ``radius`` the radius of the piece. The near
 * plane is a hundredth of the distance, never below a ten-thousandth of the
 * radius, so that zooming close to a face does not cut it away; the far plane
 * lies ten times as far as the far side of the piece, so that the grid and
 * the axes stay in view. The ratio of the two stays small enough for the
 * depth buffer next to the polygon offset.
 */
export function depthRange(distance: number, radius: number): DepthRange {
  const r = Number.isFinite(radius) && radius > 0 ? radius : 1
  const d = Number.isFinite(distance) && distance > 0 ? distance : r
  const near = Math.max(d / 100, r * NEAR_FLOOR)
  const far = Math.max((d + r) * 10, near * 100)
  return { near, far }
}

/** Whether a camera needs the new planes: a change of more than 1 %. */
export function depthChanged(current: DepthRange, wanted: DepthRange): boolean {
  const moved = (a: number, b: number) => Math.abs(a - b) > 0.01 * Math.max(a, b)
  return moved(current.near, wanted.near) || moved(current.far, wanted.far)
}

/**
 * Whether the piece is another size than the one the view was last fitted to
 * (its diagonal differs by more than 5 %); the first size, from 0, always is.
 * A size that is no positive number never is.
 */
export function sizeChanged(fitted: number, current: number): boolean {
  if (!Number.isFinite(current) || current <= 0) return false
  if (!(fitted > 0)) return true
  return Math.abs(current - fitted) > 0.05 * fitted
}
