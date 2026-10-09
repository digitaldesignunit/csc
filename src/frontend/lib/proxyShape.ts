/**
 * The one drawing of a snapshot's proxy (decision 8.85): the grey solid, its
 * edges and the deviation overlay all draw these faces, in the proxy's local
 * axes (mm), placed by one matrix. There is no second path that builds a box
 * or prism without the proxy's `placement`.
 */

import * as THREE from 'three'
import { placementMatrix, proxyFaceGeometries, type ProxyDoc } from '@/lib/proxyOverlay'

/** Stored millimetres to viewer metres. */
export const PROXY_SCALE = 0.001

export type ProxyShape = {
  /** Faces by face id, local axes (mm). */
  faces: Record<string, THREE.BufferGeometry>
  /** Edge lines of each face (30 deg threshold), local axes (mm). */
  edges: Record<string, THREE.BufferGeometry>
  /** Local axes (mm) to the viewer scene: Rhino z-up to y-up, mm to m, placement. */
  matrix: THREE.Matrix4
}

const isPositive = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0

const isPoint = (value: unknown, dimensions: number): boolean =>
  Array.isArray(value) && value.length >= dimensions
  && value.slice(0, dimensions).every((v) => typeof v === 'number' && Number.isFinite(v))

const isFrame = (placement: ProxyDoc['placement'] | null | undefined): boolean =>
  !!placement && (['o', 'x', 'y', 'z'] as const).every((axis) => isPoint(placement[axis], 3))

/** True when the proxy's parameters and placement give a shape to draw. */
export function isDrawableProxy(proxy: ProxyDoc | null | undefined): proxy is ProxyDoc {
  if (!proxy || !isFrame(proxy.placement)) return false
  const params = (proxy.params ?? {}) as Record<string, unknown>
  switch (proxy.primitive) {
    case 'box':
      return Array.isArray(params.size) && params.size.length === 3 && params.size.every(isPositive)
    case 'prism':
      return Array.isArray(params.profile) && params.profile.length >= 3
        && params.profile.every((p) => isPoint(p, 2)) && isPositive(params.height)
    case 'cylinder':
      return isPositive(params.radius) && isPositive(params.height)
    case 'hull':
      return Array.isArray(params.vertices) && params.vertices.length >= 4
        && params.vertices.every((p) => isPoint(p, 3))
        && Array.isArray(params.faces) && params.faces.length >= 4
        && params.faces.every((f) => isPoint(f, 3))
    default:
      return false
  }
}

/** Local axes (mm) to viewer scene, for a proxy's placement. */
export function proxyMatrix(placement: ProxyDoc['placement']): THREE.Matrix4 {
  return new THREE.Matrix4()
    .makeRotationX(-Math.PI / 2)
    .multiply(new THREE.Matrix4().makeScale(PROXY_SCALE, PROXY_SCALE, PROXY_SCALE))
    .multiply(placementMatrix(placement))
}

/** The faces, edges and placement of a proxy, or null when it cannot be drawn. */
export function buildProxyShape(proxy: ProxyDoc | null | undefined): ProxyShape | null {
  if (!isDrawableProxy(proxy)) return null
  const faces = proxyFaceGeometries(proxy)
  if (Object.keys(faces).length === 0) return null
  const edges = Object.fromEntries(
    Object.entries(faces).map(([face, geometry]) => [face, new THREE.EdgesGeometry(geometry, 30)]),
  )
  return { faces, edges, matrix: proxyMatrix(proxy.placement) }
}

export function disposeProxyShape(shape: ProxyShape): void {
  Object.values(shape.faces).forEach((geometry) => geometry.dispose())
  Object.values(shape.edges).forEach((geometry) => geometry.dispose())
}

/** All faces as one geometry (position and normal), local axes (mm): the solid. */
export function solidGeometry(shape: ProxyShape): THREE.BufferGeometry {
  const positions: number[] = []
  const normals: number[] = []
  for (const geometry of Object.values(shape.faces)) {
    positions.push(...Array.from(geometry.getAttribute('position').array))
    normals.push(...Array.from(geometry.getAttribute('normal').array))
  }
  const merged = new THREE.BufferGeometry()
  merged.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  merged.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3))
  return merged
}

/** Vertices of a geometry of the shape in the viewer scene (metres, y up). */
export function sceneVertices(shape: ProxyShape, geometry: THREE.BufferGeometry): THREE.Vector3[] {
  const position = geometry.getAttribute('position')
  const out: THREE.Vector3[] = []
  for (let i = 0; i < position.count; i += 1) {
    out.push(new THREE.Vector3().fromBufferAttribute(position, i).applyMatrix4(shape.matrix))
  }
  return out
}
