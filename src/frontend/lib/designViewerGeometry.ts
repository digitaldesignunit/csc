import * as THREE from 'three'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { ComponentSnapshot, SnapshotExtrusion, SnapshotGeometry, SnapshotMesh } from '@/generated/CatalogModels'
import {
  buildReinforcementBarThreeGroup,
  snapshotReinforcementsFromGeometry,
} from '@/lib/reinforcementGeometry'
import type { SnapshotMeshRouting } from '@/generated/catalogExtras'
import { snapshotMeshRoutingFromSnapshot } from '@/generated/catalogExtras'

/**
 * Design-viewer geometry stays in Rhino Z-up (CSC canonical frame).
 * Placement/orientation is applied by DesignViewer.createTransformMatrix on
 * the parent group — do not rotate meshes here (unlike ComponentViewer at
 * origin, which uses rotateX(-π/2) without an iframe matrix).
 */

export type GeometryLoadResult =
  | { success: true; meshes: THREE.Group[]; reinforcements: THREE.Group[] }
  | {
      success: false
      error: 'not_found' | 'network_error' | 'parse_error'
      message: string
    }

interface CachedGeometry {
  meshes: THREE.Group[] | null
  reinforcements: THREE.Group[]
  etag?: string
  timestamp: number
}

const geometryCache = new Map<string, CachedGeometry>()

function normalizeColors(colors: number[]): number[] {
  if (colors.length === 0) return colors
  if (colors.every((c) => c <= 1.0)) return colors
  if (colors.every((c) => c >= 0 && c <= 255)) {
    return colors.map((c) => c / 255)
  }
  return colors.map((c) => Math.max(0, Math.min(1, c)))
}

function snapshotMeshesFromGeometry(geometry: SnapshotGeometry): SnapshotMesh[] {
  const meshes = geometry.meshes
  return Array.isArray(meshes) ? (meshes as SnapshotMesh[]) : []
}

function snapshotExtrusionsFromGeometry(geometry: SnapshotGeometry): SnapshotExtrusion[] {
  const extrusions = geometry.extrusions
  return Array.isArray(extrusions) ? (extrusions as SnapshotExtrusion[]) : []
}

function plyPrimitiveIndicesForMode(
  manifest: Record<string, string[]> | null | undefined,
  mode: 'reduced' | 'detailed',
): number[] {
  if (!manifest || typeof manifest !== 'object') return []
  const role = mode === 'reduced' ? 'reduced' : 'detailed'
  return Object.keys(manifest)
    .map((k) => Number.parseInt(k, 10))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => a - b)
    .filter((idx) => {
      const roles = manifest[String(idx)]
      return Array.isArray(roles) && roles.includes(role)
    })
}

function buildThreeGroupFromPLYGeometry(
  geometry: THREE.BufferGeometry,
  meshLabel: string,
): THREE.Group {
  const colorAttr = geometry.getAttribute('color') as THREE.BufferAttribute | undefined
  if (colorAttr && colorAttr.array.length > 0) {
    const raw = Array.from(colorAttr.array as ArrayLike<number>)
    geometry.setAttribute(
      'color',
      new THREE.Float32BufferAttribute(normalizeColors(raw), colorAttr.itemSize),
    )
  }

  geometry.computeVertexNormals()
  geometry.normalizeNormals()

  const hasColors = !!geometry.getAttribute('color')
  const material = hasColors
    ? new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })
    : new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.DoubleSide })

  const mesh = new THREE.Mesh(geometry, material)
  mesh.name = meshLabel

  const object = new THREE.Group()
  object.add(mesh)
  const edgeGeometry = new THREE.EdgesGeometry(geometry)
  const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x000000 })
  const edges = new THREE.LineSegments(edgeGeometry, edgeMaterial)
  edges.name = `${meshLabel}_edges`
  object.add(edges)
  return object
}

async function loadSnapshotPlyMeshes(
  snapshotId: string,
  mode: 'reduced' | 'detailed',
  manifest: Record<string, string[]> | null | undefined,
): Promise<{ ok: true; meshes: THREE.Group[]; etag?: string } | { ok: false }> {
  const resolution = mode === 'reduced' ? 'reduced' : 'detailed'
  const indices = plyPrimitiveIndicesForMode(manifest, resolution)
  if (indices.length === 0) return { ok: false }

  const loader = new PLYLoader()
  const groups: THREE.Group[] = []
  const etags: string[] = []

  for (const primitiveIndex of indices) {
    const url = `/api/backend/snapshots/${encodeURIComponent(snapshotId)}/meshes/${primitiveIndex}/${resolution}`
    const response = await fetch(url, { credentials: 'include' })
    const etag = response.headers.get('ETag')
    if (etag) etags.push(etag)
    if (!response.ok) return { ok: false }

    const buffer = await response.arrayBuffer()
    const geom = loader.parse(buffer)
    groups.push(buildThreeGroupFromPLYGeometry(geom, `PLY Mesh ${primitiveIndex + 1}`))
  }

  if (groups.length === 0) return { ok: false }
  return {
    ok: true,
    meshes: groups,
    etag: etags.length > 0 ? etags.sort().join('|') : undefined,
  }
}

function snapshotColorRgb(snapshot: ComponentSnapshot): [number, number, number] {
  const c = snapshot.color
  return [
    Array.isArray(c) ? (c[0] as number) : 110,
    Array.isArray(c) ? (c[1] as number) : 110,
    Array.isArray(c) ? (c[2] as number) : 110,
  ]
}

function buildExtrusionGroup(
  extrusion: SnapshotExtrusion,
  label: string,
  colorRgb: [number, number, number],
): THREE.Group | null {
  const profile = extrusion.profile
  const height = extrusion.height
  if (!profile?.length || typeof height !== 'number' || !Number.isFinite(height)) {
    return null
  }

  const shape = new THREE.Shape()
  shape.moveTo(profile[0][0], profile[0][1])
  profile.forEach((p, i) => {
    if (i > 0) shape.lineTo(p[0], p[1])
  })

  const extrudeGeometry = new THREE.ExtrudeGeometry(shape, {
    steps: 2,
    depth: height,
    bevelEnabled: false,
  })
  extrudeGeometry.translate(0, 0, -height * 0.5)
  const geom =
    extrudeGeometry.index !== null ? extrudeGeometry.toNonIndexed() : extrudeGeometry
  geom.computeVertexNormals()

  const colorHex = (colorRgb[0] << 16) + (colorRgb[1] << 8) + colorRgb[2]
  const faceMesh = new THREE.Mesh(
    geom,
    new THREE.MeshBasicMaterial({ color: colorHex, side: THREE.DoubleSide }),
  )
  faceMesh.name = `extrusion_face_${label}`

  const edgeGeometry = new THREE.EdgesGeometry(geom)
  const edgeMesh = new THREE.LineSegments(
    edgeGeometry,
    new THREE.LineBasicMaterial({ color: 0x000000 }),
  )
  edgeMesh.name = `extrusion_edge_${label}`

  const group = new THREE.Group()
  group.add(faceMesh)
  group.add(edgeMesh)
  return group
}

function buildPrimitiveMeshGroup(mesh: SnapshotMesh, index: number, snapshotId: string): THREE.Group | null {
  const vertices = mesh.vertices
  const faces = mesh.faces
  if (!vertices?.length || !faces?.length) return null

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(vertices.flat(), 3),
  )
  geometry.setIndex(faces.flat())

  const colors = Array.isArray(mesh.colors) ? (mesh.colors as number[][]) : null
  if (colors && colors.length === vertices.length) {
    const flatColors = colors.flat()
    geometry.setAttribute(
      'color',
      new THREE.Float32BufferAttribute(normalizeColors(flatColors), 3),
    )
  }

  geometry.computeVertexNormals()
  geometry.normalizeNormals()

  const material =
    colors && colors.length === vertices.length
      ? new THREE.MeshBasicMaterial({ vertexColors: true, side: THREE.DoubleSide })
      : new THREE.MeshBasicMaterial({ color: 0x888888, side: THREE.DoubleSide })

  const threeMesh = new THREE.Mesh(geometry, material)
  threeMesh.name = `mesh_${index}_${snapshotId}`

  const edgeGeometry = new THREE.EdgesGeometry(geometry)
  const edgeMesh = new THREE.LineSegments(
    edgeGeometry,
    new THREE.LineBasicMaterial({ color: 0x000000 }),
  )
  edgeMesh.name = `mesh_edge_${index}_${snapshotId}`

  const group = new THREE.Group()
  group.add(threeMesh)
  group.add(edgeMesh)
  return group
}

function buildPrimitiveGroupsFromSnapshot(snapshot: ComponentSnapshot): THREE.Group[] {
  const geometry = snapshot.geometry
  const colorRgb = snapshotColorRgb(snapshot)
  const groups: THREE.Group[] = []

  for (const [idx, extr] of snapshotExtrusionsFromGeometry(geometry).entries()) {
    const group = buildExtrusionGroup(extr, `${snapshot._id}_${idx}`, colorRgb)
    if (group) groups.push(group)
  }

  for (const [idx, mesh] of snapshotMeshesFromGeometry(geometry).entries()) {
    const group = buildPrimitiveMeshGroup(mesh, idx, String(snapshot._id ?? idx))
    if (group) groups.push(group)
  }

  return groups
}

function buildReinforcementGroupsFromSnapshot(snapshot: ComponentSnapshot): THREE.Group[] {
  const snapshotId = String(snapshot._id ?? 'snapshot')
  return snapshotReinforcementsFromGeometry(snapshot.geometry)
    .map((bar, index) => buildReinforcementBarThreeGroup(
      bar,
      `reinforcement_${snapshotId}_${index}`,
    ))
    .filter((group): group is THREE.Group => group !== null)
}

export async function fetchSnapshot(snapshotId: string): Promise<ComponentSnapshot | null> {
  const response = await fetch(`/api/backend/snapshots/${encodeURIComponent(snapshotId)}`, {
    credentials: 'include',
    cache: 'no-store',
  })
  if (!response.ok) return null
  return (await response.json()) as ComponentSnapshot
}

export async function loadDesignSnapshotGeometry(
  snapshotId: string,
  mode: 'primitive' | 'reduced' | 'detailed',
): Promise<GeometryLoadResult> {
  const cacheKey = `${snapshotId}_${mode}`
  const cached = geometryCache.get(cacheKey)
  if (cached && Date.now() - cached.timestamp < 5 * 60 * 1000) {
    if (cached.meshes || cached.reinforcements.length > 0) {
      return {
        success: true,
        meshes: cached.meshes ?? [],
        reinforcements: cached.reinforcements,
      }
    }
    return {
      success: false,
      error: 'not_found',
      message: `No ${mode} geometry available for this snapshot`,
    }
  }

  try {
    const snapshot = await fetchSnapshot(snapshotId)
    if (!snapshot) {
      return {
        success: false,
        error: 'network_error',
        message: `Failed to load snapshot ${snapshotId}`,
      }
    }

    const routing: SnapshotMeshRouting = snapshotMeshRoutingFromSnapshot(snapshot)

    const reinforcements = buildReinforcementGroupsFromSnapshot(snapshot)

    if (mode === 'primitive') {
      const meshes = buildPrimitiveGroupsFromSnapshot(snapshot)
      if (meshes.length === 0 && reinforcements.length === 0) {
        return {
          success: false,
          error: 'not_found',
          message: 'No usable primitive geometry in snapshot',
        }
      }
      geometryCache.set(cacheKey, {
        meshes,
        reinforcements,
        etag: typeof snapshot.etag === 'string' ? snapshot.etag : undefined,
        timestamp: Date.now(),
      })
      return { success: true, meshes, reinforcements }
    }

    const plyResult = await loadSnapshotPlyMeshes(
      snapshotId,
      mode,
      routing.mesh_ply_resolutions as Record<string, string[]> | null | undefined,
    )
    if (plyResult.ok && plyResult.meshes.length > 0) {
      geometryCache.set(cacheKey, {
        meshes: plyResult.meshes,
        reinforcements,
        etag: plyResult.etag,
        timestamp: Date.now(),
      })
      return { success: true, meshes: plyResult.meshes, reinforcements }
    }

    if (reinforcements.length > 0) {
      geometryCache.set(cacheKey, {
        meshes: [],
        reinforcements,
        timestamp: Date.now(),
      })
      return { success: true, meshes: [], reinforcements }
    }

    geometryCache.set(cacheKey, {
      meshes: null,
      reinforcements: [],
      timestamp: Date.now(),
    })
    return {
      success: false,
      error: 'not_found',
      message: `No ${mode} PLY geometry available for this snapshot`,
    }
  } catch (error) {
    return {
      success: false,
      error: 'network_error',
      message: error instanceof Error ? error.message : 'Unknown error',
    }
  }
}
