import type { ComponentSnapshot } from '@/generated/CatalogModels'

export type GeometryDownloadItem = {
  id: string
  label: string
  filename: string
  /** Path under /api/backend (authenticated fetch). */
  url: string
  group: 'mesh_file' | 'mesh_primitive' | 'extrusion' | 'point_cloud'
}

const API = '/api/backend'

function meshPlyManifest(
  snapshot: ComponentSnapshot,
): Record<string, string[]> | null {
  const raw = snapshot.mesh_ply_resolutions
  if (raw == null || typeof raw !== 'object') return null
  return raw as Record<string, string[]>
}

function pushMeshFormatDownloads(
  items: GeometryDownloadItem[],
  opts: {
    idBase: string
    group: 'mesh_file' | 'mesh_primitive' | 'extrusion'
    labelBase: string
    filenameBase: string
    urlPath: string
  },
): void {
  items.push({
    id: `${opts.idBase}-ply`,
    group: opts.group,
    label: `${opts.labelBase} (PLY)`,
    filename: `${opts.filenameBase}.ply`,
    url: `${API}${opts.urlPath}`,
  })
  items.push({
    id: `${opts.idBase}-obj`,
    group: opts.group,
    label: `${opts.labelBase} (OBJ)`,
    filename: `${opts.filenameBase}.obj`,
    url: `${API}${opts.urlPath}?format=obj`,
  })
}

/**
 * Build download targets for the current snapshot geometry.
 * On-disk meshes stay PLY; OBJ is converted on the server at download time.
 */
export function buildGeometryDownloadItems(
  snapshotId: string,
  snapshot: ComponentSnapshot,
): GeometryDownloadItem[] {
  const items: GeometryDownloadItem[] = []
  const manifest = meshPlyManifest(snapshot)
  const geometry = snapshot.geometry as
    | {
        meshes?: unknown[]
        extrusions?: unknown[]
        point_clouds?: unknown[]
      }
    | undefined
  const enc = encodeURIComponent(snapshotId)

  if (manifest) {
    for (const key of Object.keys(manifest).sort((a, b) => Number(a) - Number(b))) {
      const idx = Number.parseInt(key, 10)
      if (!Number.isFinite(idx)) continue
      const roles = manifest[key]
      if (!Array.isArray(roles)) continue
      for (const resolution of roles) {
        if (resolution !== 'reduced' && resolution !== 'detailed') continue
        const base = `${snapshotId}_mesh_${idx}_${resolution}`
        pushMeshFormatDownloads(items, {
          idBase: `mesh-file-${idx}-${resolution}`,
          group: 'mesh_file',
          labelBase: `Mesh ${idx + 1} (${resolution})`,
          filenameBase: base,
          urlPath: `/snapshots/${enc}/meshes/${idx}/${resolution}`,
        })
      }
    }
  }

  const meshes = geometry?.meshes
  if (Array.isArray(meshes)) {
    meshes.forEach((_, index) => {
      const base = `${snapshotId}_mesh_${index}_primitive`
      pushMeshFormatDownloads(items, {
        idBase: `mesh-primitive-${index}`,
        group: 'mesh_primitive',
        labelBase: `Mesh ${index + 1} (catalog primitive)`,
        filenameBase: base,
        urlPath: `/snapshots/${enc}/meshes/${index}/primitive`,
      })
    })
  }

  const extrusions = geometry?.extrusions
  if (Array.isArray(extrusions)) {
    extrusions.forEach((_, index) => {
      const base = `${snapshotId}_extrusion_${index}`
      pushMeshFormatDownloads(items, {
        idBase: `extrusion-${index}`,
        group: 'extrusion',
        labelBase: `Extrusion ${index + 1}`,
        filenameBase: base,
        urlPath: `/snapshots/${enc}/extrusions/${index}`,
      })
    })
  }

  const pointClouds = geometry?.point_clouds
  if (Array.isArray(pointClouds)) {
    pointClouds.forEach((_, index) => {
      items.push({
        id: `point-cloud-${index}`,
        group: 'point_cloud',
        label: `Point cloud ${index + 1}`,
        filename: `${snapshotId}_point_cloud_${index}.ply`,
        url: `${API}/snapshots/${enc}/point_clouds/${index}.ply`,
      })
    })
  }

  return items
}

export async function downloadGeometryFile(
  item: GeometryDownloadItem,
): Promise<void> {
  const res = await fetch(item.url, { credentials: 'include', cache: 'no-store' })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Download failed (${res.status})`)
  }
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = item.filename
    anchor.rel = 'noopener'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(objectUrl)
  }
}

export const GEOMETRY_DOWNLOAD_GROUP_LABELS: Record<
  GeometryDownloadItem['group'],
  string
> = {
  mesh_file: 'Mesh files (on disk)',
  mesh_primitive: 'Mesh primitives (from catalog)',
  extrusion: 'Extrusions (generated mesh)',
  point_cloud: 'Point clouds',
}
