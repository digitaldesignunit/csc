'use client'

import { useMemo, useState } from 'react'
import { Download, Loader2 } from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  buildGeometryDownloadItems,
  downloadGeometryFile,
  GEOMETRY_DOWNLOAD_GROUP_LABELS,
  type GeometryDownloadItem,
} from '@/lib/snapshotGeometryDownloads'

type Props = {
  catalog: CatalogComponent
}

const GROUP_ORDER: GeometryDownloadItem['group'][] = [
  'mesh_file',
  'mesh_primitive',
  'extrusion',
  'point_cloud',
]

export default function ComponentSnapshotGeometryDownload({ catalog }: Props) {
  const { identity, snapshot } = catalog
  const snapshotId = String(snapshot._id ?? identity.current_snapshot_id ?? '')

  const items = useMemo(
    () => (snapshotId ? buildGeometryDownloadItems(snapshotId, snapshot) : []),
    [snapshot, snapshotId],
  )

  const grouped = useMemo(() => {
    const map = new Map<GeometryDownloadItem['group'], GeometryDownloadItem[]>()
    for (const item of items) {
      const list = map.get(item.group) ?? []
      list.push(item)
      map.set(item.group, list)
    }
    return map
  }, [items])

  const [open, setOpen] = useState(false)
  const [downloadingId, setDownloadingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (items.length === 0) {
    return null
  }

  const handleDownload = async (item: GeometryDownloadItem) => {
    setDownloadingId(item.id)
    setError(null)
    try {
      await downloadGeometryFile(item)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed')
    } finally {
      setDownloadingId(null)
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="w-full"
        onClick={() => {
          setError(null)
          setOpen(true)
        }}
      >
        <Download className="mr-2 h-4 w-4" />
        Download geometry
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Download geometry</DialogTitle>
            <DialogDescription>
              Meshes as PLY or OBJ (OBJ is converted on demand; nothing extra is
              stored on disk). Point clouds are PLY only.
            </DialogDescription>
          </DialogHeader>

          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          <div className="max-h-[min(60vh,24rem)] space-y-4 overflow-y-auto pr-1">
            {GROUP_ORDER.map(group => {
              const groupItems = grouped.get(group)
              if (!groupItems?.length) return null
              return (
                <section key={group} className="space-y-2">
                  <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {GEOMETRY_DOWNLOAD_GROUP_LABELS[group]}
                  </h4>
                  <ul className="space-y-1.5">
                    {groupItems.map(item => (
                      <li key={item.id}>
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          className="h-auto w-full justify-between py-2 text-left font-normal"
                          disabled={downloadingId !== null}
                          onClick={() => void handleDownload(item)}
                        >
                          <span className="min-w-0 flex-1 truncate pr-2 text-sm">
                            {item.label}
                          </span>
                          {downloadingId === item.id ? (
                            <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
                          ) : (
                            <Download className="h-4 w-4 shrink-0 opacity-60" />
                          )}
                        </Button>
                      </li>
                    ))}
                  </ul>
                </section>
              )
            })}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
