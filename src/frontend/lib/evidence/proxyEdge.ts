/**
 * Edge distance against the proxy (decision 8.135 a): a picked point (each
 * grid point) is projected onto the nearest face of the snapshot's proxy and
 * the boundary of that face is its edge. The proxy is the same for every view
 * of the piece, so the answer does not depend on what the viewer shows or on
 * how rough a scan is. Everything is in the stored coordinates (mm).
 *
 * A face is what the proxy builder calls a face (the six sides of a box, the
 * top, bottom and sides of a prism, the caps and the lateral of a cylinder);
 * a hull has one facet per run of coplanar triangles.
 */
import * as THREE from 'three'

import { distanceToSegment, type Vec3 } from '@/lib/evidence/grid'
import { placementMatrix, proxyFaceGeometries, type ProxyDoc } from '@/lib/proxyOverlay'
import { isDrawableProxy } from '@/lib/proxyShape'

const WELD_MM = 1e-3
/** triangles of a hull this close to coplanar make one facet */
const FACET_COS = Math.cos((1 * Math.PI) / 180)

type Patch = {
  triangles: THREE.Triangle[]
  box: THREE.Box3
  /** edges used by one triangle of the face only */
  boundary: [Vec3, Vec3][]
}

export type ProxyEdgeModel = { patches: Patch[] }

function boundaryOf(triangles: THREE.Triangle[]): [Vec3, Vec3][] {
  const ids = new Map<string, number>()
  const points: THREE.Vector3[] = []
  const idOf = (p: THREE.Vector3) => {
    const key = `${Math.round(p.x / WELD_MM)},${Math.round(p.y / WELD_MM)},${Math.round(p.z / WELD_MM)}`
    let id = ids.get(key)
    if (id === undefined) {
      id = points.length
      ids.set(key, id)
      points.push(p)
    }
    return id
  }
  const uses = new Map<string, number>()
  for (const t of triangles) {
    const corners = [idOf(t.a), idOf(t.b), idOf(t.c)]
    for (let k = 0; k < 3; k += 1) {
      const p = corners[k]
      const q = corners[(k + 1) % 3]
      if (p === q) continue
      const key = p < q ? `${p}-${q}` : `${q}-${p}`
      uses.set(key, (uses.get(key) ?? 0) + 1)
    }
  }
  const out: [Vec3, Vec3][] = []
  for (const [key, count] of uses) {
    if (count !== 1) continue
    const [p, q] = key.split('-').map(Number)
    out.push([[points[p].x, points[p].y, points[p].z], [points[q].x, points[q].y, points[q].z]])
  }
  return out
}

function patchOf(triangles: THREE.Triangle[]): Patch | null {
  if (triangles.length === 0) return null
  const box = new THREE.Box3()
  for (const t of triangles) box.expandByPoint(t.a).expandByPoint(t.b).expandByPoint(t.c)
  return { triangles, box, boundary: boundaryOf(triangles) }
}

/** Runs of triangles that share an edge and face alike: the facets of a hull. */
function facets(triangles: THREE.Triangle[]): THREE.Triangle[][] {
  const normals = triangles.map((t) => t.getNormal(new THREE.Vector3()))
  const keyOf = (p: THREE.Vector3) => `${Math.round(p.x / WELD_MM)},${Math.round(p.y / WELD_MM)},${Math.round(p.z / WELD_MM)}`
  const byEdge = new Map<string, number[]>()
  triangles.forEach((t, i) => {
    const corners = [keyOf(t.a), keyOf(t.b), keyOf(t.c)]
    for (let k = 0; k < 3; k += 1) {
      const p = corners[k]
      const q = corners[(k + 1) % 3]
      const key = p < q ? `${p}|${q}` : `${q}|${p}`
      const list = byEdge.get(key)
      if (list) list.push(i)
      else byEdge.set(key, [i])
    }
  })
  const group = new Array<number>(triangles.length).fill(-1)
  const out: THREE.Triangle[][] = []
  for (let i = 0; i < triangles.length; i += 1) {
    if (group[i] >= 0) continue
    const members: THREE.Triangle[] = []
    const stack = [i]
    group[i] = out.length
    while (stack.length) {
      const t = stack.pop() as number
      members.push(triangles[t])
      const corners = [keyOf(triangles[t].a), keyOf(triangles[t].b), keyOf(triangles[t].c)]
      for (let k = 0; k < 3; k += 1) {
        const p = corners[k]
        const q = corners[(k + 1) % 3]
        const key = p < q ? `${p}|${q}` : `${q}|${p}`
        for (const other of byEdge.get(key) ?? []) {
          if (group[other] >= 0) continue
          if (normals[other].dot(normals[i]) >= FACET_COS && normals[other].dot(normals[t]) >= FACET_COS) {
            group[other] = out.length
            stack.push(other)
          }
        }
      }
    }
    out.push(members)
  }
  return out
}

/** The faces of a proxy in stored coordinates, or null when it cannot be drawn. */
export function proxyEdgeModel(proxy: ProxyDoc | null | undefined): ProxyEdgeModel | null {
  if (!isDrawableProxy(proxy)) return null
  const faces = proxyFaceGeometries(proxy)
  const matrix = placementMatrix(proxy.placement)
  const patches: Patch[] = []
  for (const [id, geometry] of Object.entries(faces)) {
    const position = geometry.getAttribute('position')
    const triangles: THREE.Triangle[] = []
    for (let i = 0; i + 2 < position.count; i += 3) {
      const corner = (k: number) => new THREE.Vector3().fromBufferAttribute(position, i + k).applyMatrix4(matrix)
      const triangle = new THREE.Triangle(corner(0), corner(1), corner(2))
      if (triangle.getArea() > 0) triangles.push(triangle)
    }
    geometry.dispose()
    const parts = proxy.primitive === 'hull' && id === 'sphere' ? facets(triangles) : [triangles]
    for (const part of parts) {
      const patch = patchOf(part)
      if (patch) patches.push(patch)
    }
  }
  return patches.length ? { patches } : null
}

const SCRATCH = new THREE.Vector3()
const CLOSEST = new THREE.Vector3()

/**
 * Distance from each point to the boundary of the proxy face nearest to it,
 * measured from the point's projection onto that face (a point beside the
 * face projects onto its rim: distance 0).
 */
export function proxyEdgeDistances(model: ProxyEdgeModel, points: Vec3[]): number[] {
  return points.map((point) => {
    const p = SCRATCH.set(point[0], point[1], point[2])
    let best = Infinity
    let bestPatch: Patch | null = null
    let projected: Vec3 = point
    for (const patch of model.patches) {
      if (patch.box.distanceToPoint(p) >= best) continue
      for (const triangle of patch.triangles) {
        triangle.closestPointToPoint(p, CLOSEST)
        const d = CLOSEST.distanceTo(p)
        if (d < best) {
          best = d
          bestPatch = patch
          projected = [CLOSEST.x, CLOSEST.y, CLOSEST.z]
        }
      }
    }
    if (!bestPatch) return Infinity
    let edge = Infinity
    for (const [a, b] of (bestPatch as Patch).boundary) {
      const d = distanceToSegment(projected, a, b)
      if (d < edge) edge = d
    }
    return edge
  })
}

/** Distances and the indices closer than `minEdgeMm`. */
export function proxyEdgeWarnings(
  model: ProxyEdgeModel,
  points: Vec3[],
  minEdgeMm: number,
): { distances: (number | null)[]; tooClose: number[] } {
  const distances = proxyEdgeDistances(model, points)
  return {
    distances,
    tooClose: distances.flatMap((d, i) => (d < minEdgeMm ? [i] : [])),
  }
}
