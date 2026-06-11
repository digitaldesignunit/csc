import * as THREE from 'three'
import { PLYLoader } from 'three/examples/jsm/loaders/PLYLoader.js'
import type { SnapshotGeometry, SnapshotPointCloud } from '@/generated/CatalogModels'

export const DEFAULT_POINT_CLOUD_COLOR = 0x888888
/** Screen-space point size (pixels) when sizeAttenuation is false. */
export const POINT_CLOUD_DISPLAY_SIZE = 4

function normalizeColors(colors: number[]): number[] {
  if (colors.length === 0) return colors
  if (colors.every((c) => c <= 1.0)) return colors
  if (colors.every((c) => c >= 0 && c <= 255)) {
    return colors.map((c) => c / 255)
  }
  return colors.map((c) => Math.max(0, Math.min(1, c)))
}

function vertexColorsFromSnapshot(
  colors: number[][] | unknown | undefined,
): number[][] | undefined {
  if (colors == null || !Array.isArray(colors) || colors.length === 0) {
    return undefined
  }
  if (!colors.every((c) => Array.isArray(c))) {
    return undefined
  }
  return colors as number[][]
}

export function snapshotPointCloudsFromGeometry(
  geometry: SnapshotGeometry,
): SnapshotPointCloud[] {
  const pointClouds = geometry.point_clouds
  if (!Array.isArray(pointClouds)) return []
  return (pointClouds as SnapshotPointCloud[]).filter((pc) => (
    Array.isArray(pc?.points)
    && pc.points.length > 0
    && pc.points.every((pt) => Array.isArray(pt) && pt.length >= 3)
  ))
}

function buildPointsObject(
  geometry: THREE.BufferGeometry,
  name: string,
  defaultColor: number = DEFAULT_POINT_CLOUD_COLOR,
): THREE.Points | null {
  const position = geometry.getAttribute('position') as THREE.BufferAttribute | undefined
  if (!position || position.count === 0) return null

  const colorAttr = geometry.getAttribute('color') as THREE.BufferAttribute | undefined
  const hasColors = !!colorAttr && colorAttr.count > 0

  if (hasColors && colorAttr) {
    const raw = Array.from(colorAttr.array as ArrayLike<number>)
    geometry.setAttribute(
      'color',
      new THREE.Float32BufferAttribute(normalizeColors(raw), colorAttr.itemSize),
    )
  }

  const material = hasColors
    ? new THREE.PointsMaterial({
        size: POINT_CLOUD_DISPLAY_SIZE,
        sizeAttenuation: false,
        vertexColors: true,
      })
    : new THREE.PointsMaterial({
        size: POINT_CLOUD_DISPLAY_SIZE,
        sizeAttenuation: false,
        color: defaultColor,
      })

  const points = new THREE.Points(geometry, material)
  points.name = name
  return points
}

export function buildPointCloudThreeGroup(
  pointCloud: SnapshotPointCloud,
  name: string,
  defaultColor: number = DEFAULT_POINT_CLOUD_COLOR,
): THREE.Group | null {
  const positions = pointCloud.points.flat()
  if (positions.length < 3) return null

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(positions, 3),
  )

  const colors = vertexColorsFromSnapshot(pointCloud.colors)
  if (colors && colors.length === pointCloud.points.length) {
    geometry.setAttribute(
      'color',
      new THREE.Float32BufferAttribute(normalizeColors(colors.flat()), 3),
    )
  }

  const points = buildPointsObject(geometry, name, defaultColor)
  if (!points) return null

  const group = new THREE.Group()
  group.name = name
  group.add(points)
  return group
}

export function buildPointCloudGroupFromPlyBuffer(
  buffer: ArrayBuffer,
  name: string,
  options?: {
    defaultColor?: number
    /** ComponentViewer: Rhino Z-up → Three.js Y-up + mm scale on parent. */
    applyComponentViewerFrame?: boolean
    scale?: number
  },
): THREE.Group | null {
  const loader = new PLYLoader()
  const geometry = loader.parse(buffer)

  const index = geometry.getIndex()
  if (index && index.count > 0) {
    geometry.setIndex(null)
  }

  const points = buildPointsObject(
    geometry,
    name,
    options?.defaultColor ?? DEFAULT_POINT_CLOUD_COLOR,
  )
  if (!points) return null

  const group = new THREE.Group()
  group.name = name
  group.add(points)

  if (options?.applyComponentViewerFrame) {
    const scale = options.scale ?? 0.001
    group.scale.set(scale, scale, scale)
    group.rotation.x = -Math.PI / 2
  }

  return group
}

export function buildPointCloudGroupsFromSnapshot(
  snapshotId: string,
  geometry: SnapshotGeometry,
): THREE.Group[] {
  return snapshotPointCloudsFromGeometry(geometry)
    .map((pc, index) => buildPointCloudThreeGroup(
      pc,
      `point_cloud_${snapshotId}_${index}`,
    ))
    .filter((group): group is THREE.Group => group !== null)
}

export async function loadSnapshotPointCloudPlyGroups(
  snapshotId: string,
  pointCloudCount: number,
  options?: {
    applyComponentViewerFrame?: boolean
    scale?: number
  },
): Promise<{ ok: true; groups: THREE.Group[]; etag?: string } | { ok: false }> {
  if (pointCloudCount <= 0) return { ok: false }

  const groups: THREE.Group[] = []
  const etags: string[] = []

  for (let index = 0; index < pointCloudCount; index += 1) {
    const url = `/api/backend/snapshots/${encodeURIComponent(snapshotId)}/point_clouds/${index}.ply`
    try {
      const response = await fetch(url, { credentials: 'include' })
      const etag = response.headers.get('ETag')
      if (etag) etags.push(etag)
      if (!response.ok) return { ok: false }

      const buffer = await response.arrayBuffer()
      const group = buildPointCloudGroupFromPlyBuffer(
        buffer,
        `PLY Point Cloud ${index + 1}`,
        options,
      )
      if (group) groups.push(group)
    } catch {
      return { ok: false }
    }
  }

  if (groups.length === 0) return { ok: false }
  return {
    ok: true,
    groups,
    etag: etags.length > 0 ? etags.sort().join('|') : undefined,
  }
}
