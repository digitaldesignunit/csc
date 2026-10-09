/**
 * Picking on the viewer (decision 8.43): a ray hit on a mesh or an authored
 * prism, the nearest point of a point cloud within a screen tolerance. A
 * hit is reported in the stored coordinates of the snapshot (mm, Rhino
 * Z-up), never in the canonical frame: the scene's pick root holds the
 * geometry as the viewer draws it, metres with Z-up turned to Y-up, so the
 * conversion is the inverse of that turn.
 */
import * as THREE from 'three'

import type { Edge, Vec3 } from '@/lib/evidence/grid'
import { dot, scale as scaleVec, unit } from '@/lib/evidence/grid'

const MM_PER_M = 1000

/** Scene metres in the pick root's space --> stored mm (inverse of the Z-up turn). */
export function localToStored(v: THREE.Vector3): Vec3 {
  return [v.x * MM_PER_M, -v.z * MM_PER_M, v.y * MM_PER_M]
}

/** Stored mm --> scene metres in the pick root's space. */
export function storedToLocal(p: Vec3): [number, number, number] {
  return [p[0] / MM_PER_M, p[2] / MM_PER_M, -p[1] / MM_PER_M]
}

/** A direction (no scaling) from scene space to stored space. */
function directionToStored(v: THREE.Vector3): Vec3 {
  return [v.x, -v.z, v.y]
}

export type PickHit = {
  kind: 'mesh' | 'cloud'
  point: Vec3
  /** unit normal of the face (a cloud: estimated), pointing at the viewer */
  normal: Vec3 | null
  /** boundary of the planar face patch, for the edge warning; null: unknown */
  edges: Edge[] | null
  /** what the patch is, for the note under the grid tool */
  patch: 'face' | 'estimated-plane' | null
}

function chainVisible(object: THREE.Object3D, root: THREE.Object3D): boolean {
  let node: THREE.Object3D | null = object
  while (node) {
    if (!node.visible || node.userData?.noPick) return false
    if (node === root) return true
    node = node.parent
  }
  return false
}

type Candidate = {
  hit: THREE.Intersection
  object: THREE.Object3D
}

/**
 * Casts `raycaster` (already aimed) at the geometry under `root`. A cloud
 * point must lie within `pointTolerance` (world units at the point's depth)
 * of the ray; a surface in front of the nearest such point hides it.
 */
export function pickGeometry(
  raycaster: THREE.Raycaster,
  root: THREE.Object3D,
  pointTolerance: number,
): PickHit | null {
  // surfaces first; a cloud's tolerance is set per object below (three.js
  // takes the threshold in the cloud's local units, which differ from the
  // world's by the scale of its parents)
  raycaster.params.Points = { threshold: 0 }
  const meshHits: Candidate[] = []
  const pointHits: Candidate[] = []
  for (const hit of raycaster.intersectObject(root, true)) {
    if (!chainVisible(hit.object, root)) continue
    if ((hit.object as THREE.Mesh).isMesh) meshHits.push({ hit, object: hit.object })
  }
  const scale = new THREE.Vector3()
  root.traverse((object) => {
    if (!(object as THREE.Points).isPoints || !chainVisible(object, root)) return
    scale.setFromMatrixScale(object.matrixWorld)
    const world = (scale.x + scale.y + scale.z) / 3
    const own = (object.scale.x + object.scale.y + object.scale.z) / 3
    raycaster.params.Points = { threshold: (pointTolerance / Math.max(world, 1e-9)) * own }
    const found: THREE.Intersection[] = []
    object.raycast(raycaster, found)
    for (const hit of found) pointHits.push({ hit: { ...hit, object }, object })
  })
  meshHits.sort((a, b) => a.hit.distance - b.hit.distance)
  pointHits.sort((a, b) => (a.hit.distanceToRay ?? 0) - (b.hit.distanceToRay ?? 0))
  const surface = meshHits[0]
  const cloudPoint = pointHits[0]
  if (cloudPoint && (!surface || cloudPoint.hit.distance <= surface.hit.distance + pointTolerance)) {
    return cloudHit(cloudPoint, root, raycaster)
  }
  if (surface) return meshHit(surface, root, raycaster)
  return null
}

function worldToStored(world: THREE.Vector3, root: THREE.Object3D): Vec3 {
  return localToStored(root.worldToLocal(world.clone()))
}

function vertexWorld(mesh: THREE.Mesh, index: number): THREE.Vector3 {
  const position = mesh.geometry.getAttribute('position')
  return new THREE.Vector3().fromBufferAttribute(position as THREE.BufferAttribute, index)
    .applyMatrix4(mesh.matrixWorld)
}

function meshHit(candidate: Candidate, root: THREE.Object3D, raycaster: THREE.Raycaster): PickHit {
  const mesh = candidate.object as THREE.Mesh
  const { hit } = candidate
  const point = worldToStored(hit.point, root)
  let normal: Vec3 | null = null
  let edges: Edge[] | null = null
  if (hit.face) {
    const a = root.worldToLocal(vertexWorld(mesh, hit.face.a))
    const b = root.worldToLocal(vertexWorld(mesh, hit.face.b))
    const c = root.worldToLocal(vertexWorld(mesh, hit.face.c))
    const n = new THREE.Vector3().subVectors(b, a).cross(new THREE.Vector3().subVectors(c, a)).normalize()
    // a double-sided face: the normal looks at the viewer
    const toViewer = root.worldToLocal(raycaster.ray.origin.clone().add(raycaster.ray.direction.clone().multiplyScalar(-1)))
      .sub(root.worldToLocal(raycaster.ray.origin.clone()))
    const direction = toViewer.lengthSq() > 0 ? toViewer : n
    if (n.dot(direction) < 0) n.negate()
    normal = unit(directionToStored(n))
    if (normal && hit.faceIndex !== undefined && hit.faceIndex !== null) {
      edges = facePatchEdges(mesh, hit.faceIndex, root)
    }
  }
  return { kind: 'mesh', point, normal, edges, patch: edges ? 'face' : null }
}

// FACE PATCH ------------------------------------------------------------------
const PLANAR_COS = Math.cos((4 * Math.PI) / 180)
/** a patch of fewer triangles is not a flat face (a scanned, noisy surface) */
const MIN_PATCH_TRIANGLES = 6
/**
 * a mesh this small is a proxy (an authored box has two triangles a face, a
 * fitted hull one a facet): its faces are flat by construction
 */
const LOW_POLY_TRIANGLES = 500
const MAX_TRIANGLES = 400_000
const WELD_M = 1e-4 // 0.1 mm

type PatchAnalysis = {
  /** where the mesh sat in the root when this was built */
  signature: string
  points: THREE.Vector3[]
  corner: (t: number, k: number) => number
  triangles: number
  normals: (THREE.Vector3 | null)[]
  edgeUsers: Map<string, number[]>
} | null

// the welding and the triangle graph of a mesh are built once, not per pick
const ANALYSIS = new WeakMap<THREE.BufferGeometry, PatchAnalysis>()

function analyse(mesh: THREE.Mesh, root: THREE.Object3D): PatchAnalysis {
  const geometry = mesh.geometry
  const signature = new THREE.Matrix4()
    .copy(root.matrixWorld).invert().multiply(mesh.matrixWorld).elements.join(',')
  const cached = ANALYSIS.get(geometry)
  if (cached !== undefined && (cached === null || cached.signature === signature)) return cached
  const position = geometry.getAttribute('position') as THREE.BufferAttribute | undefined
  if (!position) return null
  const index = geometry.getIndex()
  const triangles = index ? index.count / 3 : position.count / 3
  if (!Number.isInteger(triangles) || triangles > MAX_TRIANGLES) {
    ANALYSIS.set(geometry, null)
    return null
  }

  // welded vertex ids, positions in the root's space
  const ids = new Map<string, number>()
  const points: THREE.Vector3[] = []
  const vertexId: number[] = new Array(position.count)
  const local = new THREE.Vector3()
  for (let i = 0; i < position.count; i += 1) {
    local.fromBufferAttribute(position, i).applyMatrix4(mesh.matrixWorld)
    root.worldToLocal(local)
    const key = `${Math.round(local.x / WELD_M)},${Math.round(local.y / WELD_M)},${Math.round(local.z / WELD_M)}`
    let id = ids.get(key)
    if (id === undefined) {
      id = points.length
      ids.set(key, id)
      points.push(local.clone())
    }
    vertexId[i] = id
  }
  const corner = (t: number, k: number) => vertexId[index ? index.getX(t * 3 + k) : t * 3 + k]

  const normals: (THREE.Vector3 | null)[] = new Array(triangles)
  const edgeUsers = new Map<string, number[]>()
  for (let t = 0; t < triangles; t += 1) {
    const [a, b, c] = [corner(t, 0), corner(t, 1), corner(t, 2)]
    if (a === b || b === c || a === c) {
      normals[t] = null
      continue
    }
    const n = new THREE.Vector3()
      .subVectors(points[b], points[a])
      .cross(new THREE.Vector3().subVectors(points[c], points[a]))
    normals[t] = n.lengthSq() > 0 ? n.normalize() : null
    for (const [p, q] of [[a, b], [b, c], [c, a]]) {
      const key = p < q ? `${p}-${q}` : `${q}-${p}`
      const users = edgeUsers.get(key)
      if (users) users.push(t)
      else edgeUsers.set(key, [t])
    }
  }
  const built: PatchAnalysis = { signature, points, corner, triangles, normals, edgeUsers }
  ANALYSIS.set(geometry, built)
  return built
}

/**
 * The boundary of the planar patch the hit triangle belongs to: triangles
 * sharing an edge and facing within 4 degrees of each other, vertices
 * welded at 0.1 mm. Edges used by one patch triangle only are the boundary.
 * The mesh analysis behind it is cached per geometry.
 */
export function facePatchEdges(
  mesh: THREE.Mesh,
  faceIndex: number,
  root: THREE.Object3D,
): Edge[] | null {
  const analysis = analyse(mesh, root)
  if (!analysis) return null
  const { points, corner, triangles, normals, edgeUsers } = analysis
  const start = normals[faceIndex]
  if (!start) return null

  const inPatch = new Uint8Array(triangles)
  const stack = [faceIndex]
  inPatch[faceIndex] = 1
  while (stack.length) {
    const t = stack.pop() as number
    const n = normals[t] as THREE.Vector3
    const [a, b, c] = [corner(t, 0), corner(t, 1), corner(t, 2)]
    for (const [p, q] of [[a, b], [b, c], [c, a]]) {
      const key = p < q ? `${p}-${q}` : `${q}-${p}`
      for (const other of edgeUsers.get(key) ?? []) {
        if (inPatch[other] || !normals[other]) continue
        // same plane: facing alike (either side) and near the start's plane
        const m = normals[other] as THREE.Vector3
        if (Math.abs(m.dot(start)) >= PLANAR_COS && Math.abs(n.dot(m)) >= PLANAR_COS) {
          inPatch[other] = 1
          stack.push(other)
        }
      }
    }
  }

  let patchSize = 0
  for (let t = 0; t < triangles; t += 1) patchSize += inPatch[t]
  if (patchSize < (triangles <= LOW_POLY_TRIANGLES ? 1 : MIN_PATCH_TRIANGLES)) return null

  const boundary: Edge[] = []
  for (const [key, users] of edgeUsers) {
    const inside = users.filter((t) => inPatch[t]).length
    if (inside === 1) {
      const [p, q] = key.split('-').map(Number)
      boundary.push([localToStored(points[p]), localToStored(points[q])])
    }
  }
  return boundary.length ? boundary : null
}

// POINT CLOUD -----------------------------------------------------------------
const NEIGHBOURS = 48

function cloudHit(candidate: Candidate, root: THREE.Object3D, raycaster: THREE.Raycaster): PickHit {
  const points = candidate.object as THREE.Points
  const position = points.geometry.getAttribute('position') as THREE.BufferAttribute
  const index = candidate.hit.index ?? 0
  const world = new THREE.Vector3().fromBufferAttribute(position, index).applyMatrix4(points.matrixWorld)
  const local = root.worldToLocal(world.clone())
  const stored = localToStored(local)
  let normal = estimateNormal(points, root, local)
  if (normal) {
    const view = root.worldToLocal(raycaster.ray.origin.clone()).sub(local)
    const toViewer = directionToStored(view)
    if (dot(normal, toViewer) < 0) normal = scaleVec(normal, -1)
  }
  return { kind: 'cloud', point: stored, normal, edges: null, patch: normal ? 'estimated-plane' : null }
}

/** Normal of the plane through the nearest neighbours (smallest principal axis). */
function estimateNormal(points: THREE.Points, root: THREE.Object3D, around: THREE.Vector3): Vec3 | null {
  const position = points.geometry.getAttribute('position') as THREE.BufferAttribute
  const count = position.count
  if (count < 8) return null
  const scratch = new THREE.Vector3()
  const nearest: { d: number; p: THREE.Vector3 }[] = []
  let worst = Infinity
  for (let i = 0; i < count; i += 1) {
    scratch.fromBufferAttribute(position, i).applyMatrix4(points.matrixWorld)
    root.worldToLocal(scratch)
    const d = scratch.distanceToSquared(around)
    if (nearest.length < NEIGHBOURS || d < worst) {
      nearest.push({ d, p: scratch.clone() })
      if (nearest.length > NEIGHBOURS) {
        nearest.sort((a, b) => a.d - b.d)
        nearest.length = NEIGHBOURS
      }
      if (nearest.length === NEIGHBOURS) worst = nearest[NEIGHBOURS - 1].d
    }
  }
  const mean = new THREE.Vector3()
  nearest.forEach(({ p }) => mean.add(p))
  mean.multiplyScalar(1 / nearest.length)
  // covariance
  const c = [0, 0, 0, 0, 0, 0] // xx xy xz yy yz zz
  for (const { p } of nearest) {
    const x = p.x - mean.x
    const y = p.y - mean.y
    const z = p.z - mean.z
    c[0] += x * x
    c[1] += x * y
    c[2] += x * z
    c[3] += y * y
    c[4] += y * z
    c[5] += z * z
  }
  const axis = smallestEigenvector([
    [c[0], c[1], c[2]],
    [c[1], c[3], c[4]],
    [c[2], c[4], c[5]],
  ])
  return axis ? unit(directionToStored(new THREE.Vector3(...axis))) : null
}

/** Jacobi iteration for a symmetric 3x3: the eigenvector of the smallest eigenvalue. */
function smallestEigenvector(m: number[][]): [number, number, number] | null {
  const a = m.map((row) => [...row])
  const v = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
  for (let sweep = 0; sweep < 24; sweep += 1) {
    let p = 0
    let q = 1
    let largest = Math.abs(a[0][1])
    if (Math.abs(a[0][2]) > largest) { p = 0; q = 2; largest = Math.abs(a[0][2]) }
    if (Math.abs(a[1][2]) > largest) { p = 1; q = 2; largest = Math.abs(a[1][2]) }
    if (largest < 1e-18) break
    const theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
    const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1))
    const cos = 1 / Math.sqrt(t * t + 1)
    const sin = t * cos
    for (let k = 0; k < 3; k += 1) {
      const akp = a[k][p]
      const akq = a[k][q]
      a[k][p] = cos * akp - sin * akq
      a[k][q] = sin * akp + cos * akq
    }
    for (let k = 0; k < 3; k += 1) {
      const apk = a[p][k]
      const aqk = a[q][k]
      a[p][k] = cos * apk - sin * aqk
      a[q][k] = sin * apk + cos * aqk
    }
    for (let k = 0; k < 3; k += 1) {
      const vkp = v[k][p]
      const vkq = v[k][q]
      v[k][p] = cos * vkp - sin * vkq
      v[k][q] = sin * vkp + cos * vkq
    }
  }
  const values = [a[0][0], a[1][1], a[2][2]]
  const smallest = values.indexOf(Math.min(...values))
  const vec: Vec3 = [v[0][smallest], v[1][smallest], v[2][smallest]]
  const normalized = unit(vec)
  return normalized ? (normalized as [number, number, number]) : null
}
