import type { ComponentSnapshot } from '@/generated/CatalogModels'

export type GeometryDownloadItem = {
  id: string
  label: string
  filename: string
  /** Path under /api/backend (authenticated fetch). */
  url: string
  group: DownloadGroup
}

/** Download groups by detail level (decision 8.23). */
export type DownloadGroup = 'proxy' | 'preview' | 'reduced' | 'original' | 'point_cloud'

/** "Mesh", or "Mesh 2" when a snapshot has more than one (8.23). */
function numbered(base: string, index: number, count: number): string {
  return count > 1 ? `${base} ${index + 1}` : base
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
    group: Exclude<DownloadGroup, 'point_cloud'>
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
 * Stored files stay PLY; OBJ is converted on the server at download time.
 * The original mesh is stored as `detailed.ply` (decision 8.23).
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
        proxies?: { primitive?: string }[]
        point_clouds?: unknown[]
      }
    | undefined
  const enc = encodeURIComponent(snapshotId)

  const meshes = geometry?.meshes
  const meshCount = Array.isArray(meshes) ? meshes.length : 0

  if (manifest) {
    const keys = Object.keys(manifest).sort((a, b) => Number(a) - Number(b))
    const fileCount = Math.max(meshCount, keys.length)
    for (const key of keys) {
      const idx = Number.parseInt(key, 10)
      if (!Number.isFinite(idx)) continue
      const roles = manifest[key]
      if (!Array.isArray(roles)) continue
      for (const resolution of roles) {
        if (resolution !== 'reduced' && resolution !== 'detailed') continue
        const level = resolution === 'detailed' ? 'original' : 'reduced'
        const name = level === 'original' ? 'Original mesh' : 'Reduced mesh'
        pushMeshFormatDownloads(items, {
          idBase: `mesh-${level}-${idx}`,
          group: level,
          labelBase: numbered(name, idx, fileCount),
          filenameBase: `${snapshotId}_mesh_${idx}_${level}`,
          urlPath: `/snapshots/${enc}/meshes/${idx}/${resolution}`,
        })
      }
    }
  }

  if (Array.isArray(meshes)) {
    meshes.forEach((_, index) => {
      pushMeshFormatDownloads(items, {
        idBase: `mesh-preview-${index}`,
        group: 'preview',
        labelBase: numbered('Mesh preview', index, meshCount),
        filenameBase: `${snapshotId}_mesh_${index}_preview`,
        urlPath: `/snapshots/${enc}/meshes/${index}/preview`,
      })
    })
  }

  // prism proxies (authored L x W x H boxes, GH extrusions) export as meshes
  const proxies = geometry?.proxies
  if (Array.isArray(proxies)) {
    const prismCount = proxies.filter((proxy) => proxy?.primitive === 'prism').length
    proxies.forEach((proxy, index) => {
      if (proxy?.primitive !== 'prism') return
      const base = `${snapshotId}_proxy_${index}`
      pushMeshFormatDownloads(items, {
        idBase: `proxy-${index}`,
        group: 'proxy',
        labelBase: numbered('Prism proxy', index, prismCount),
        filenameBase: base,
        urlPath: `/snapshots/${enc}/proxies/${index}/mesh`,
      })
    })
  }

  const pointClouds = geometry?.point_clouds
  if (Array.isArray(pointClouds)) {
    // the server sends the original when stored, else the preview
    pointClouds.forEach((_, index) => {
      items.push({
        id: `point-cloud-${index}`,
        group: 'point_cloud',
        label: `${numbered('Point cloud', index, pointClouds.length)} (PLY)`,
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
  proxy: 'Proxies',
  preview: 'Previews',
  reduced: 'Reduced meshes',
  original: 'Originals',
  point_cloud: 'Point clouds (original where stored, else preview)',
}
