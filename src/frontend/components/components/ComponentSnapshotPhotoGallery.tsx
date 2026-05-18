'use client'

import { useCallback, useEffect, useState } from 'react'
import Image from 'next/image'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { Camera, Loader2, X, ZoomIn } from 'lucide-react'

import SnapshotPhotoCapture from '@/components/photos/SnapshotPhotoCapture'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { snapshotPhotoUrl } from '@/lib/snapshotPhotos'

async function probePhotoIndex(snapshotId: string, index: number): Promise<boolean> {
  try {
    const res = await fetch(snapshotPhotoUrl(snapshotId, index), {
      method: 'HEAD',
      credentials: 'include',
      cache: 'no-store',
    })
    return res.ok
  } catch {
    return false
  }
}

async function discoverPhotoIndices(snapshotId: string, photoCount: number): Promise<number[]> {
  const expected =
    typeof photoCount === 'number' && Number.isFinite(photoCount)
      ? Math.max(0, Math.floor(photoCount))
      : 0
  if (expected === 0) {
    return []
  }

  const found: number[] = []
  for (let index = 0; index < 32 && found.length < expected; index += 1) {
    if (await probePhotoIndex(snapshotId, index)) {
      found.push(index)
    }
  }
  return found
}

type ComponentSnapshotPhotoGalleryProps = {
  snapshotId: string
  photoCountHint?: number
  compact?: boolean
}

export default function ComponentSnapshotPhotoGallery({
  snapshotId,
  photoCountHint = 0,
  compact = false,
}: ComponentSnapshotPhotoGalleryProps) {
  const router = useRouter()
  const { data: session } = useSession()
  const isAdmin = session?.user?.role === 'admin'

  const [indices, setIndices] = useState<number[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)

  const refreshPhotos = useCallback(async () => {
    if (!snapshotId) {
      setIndices([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const found = await discoverPhotoIndices(snapshotId, photoCountHint)
      setIndices(found)
    } catch {
      setError('Failed to load photos.')
      setIndices([])
    } finally {
      setLoading(false)
    }
  }, [snapshotId, photoCountHint])

  useEffect(() => {
    refreshPhotos()
  }, [refreshPhotos])

  const gridClass = compact
    ? 'flex flex-wrap gap-2'
    : 'grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4'

  const thumbClass = compact
    ? 'group relative size-16 shrink-0 overflow-hidden rounded-md border border-border bg-muted sm:size-[4.5rem]'
    : 'group relative aspect-square overflow-hidden rounded-lg border border-border bg-muted'

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0 py-4">
          <div>
            <CardTitle className={`flex items-center gap-2 ${compact ? 'text-base' : 'text-lg'}`}>
              <Camera className="h-4 w-4 shrink-0" />
              Snapshot photos
            </CardTitle>
            {!compact && (
              <CardDescription className="mt-1">
                User-uploaded images for the current snapshot (not the 3D preview).
              </CardDescription>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          ) : isAdmin ? (
            <SnapshotPhotoCapture
              mode="live"
              snapshotId={snapshotId}
              indices={indices}
              onChange={async () => {
                await refreshPhotos()
                router.refresh()
              }}
              compact={compact}
            />
          ) : indices.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No photos for this snapshot yet.
            </p>
          ) : (
            <>
              <div className={gridClass}>
                {indices.map(index => (
                  <div key={index} className={thumbClass}>
                    <button
                      type="button"
                      className="relative h-full w-full"
                      onClick={() => setLightboxIndex(index)}
                      aria-label={`View photo ${index + 1}`}
                    >
                      <Image
                        src={snapshotPhotoUrl(snapshotId, index)}
                        alt={`Snapshot photo ${index + 1}`}
                        fill
                        className="object-cover transition-opacity group-hover:opacity-90"
                        unoptimized
                        sizes={compact ? '72px' : '(max-width: 640px) 50vw, 20vw'}
                      />
                      <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                        #{index}
                      </span>
                      <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/20 group-hover:opacity-100">
                        <ZoomIn className="h-6 w-6 text-white drop-shadow" />
                      </span>
                    </button>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                {indices.length} photo{indices.length === 1 ? '' : 's'} for this snapshot
              </p>
            </>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={lightboxIndex !== null}
        onOpenChange={open => {
          if (!open) setLightboxIndex(null)
        }}
      >
        <DialogContent className="max-w-4xl overflow-hidden p-0">
          <DialogHeader className="p-4 pb-0">
            <DialogTitle>Snapshot photo</DialogTitle>
            <DialogDescription>
              {lightboxIndex !== null ? `Slot #${lightboxIndex}` : ''}
            </DialogDescription>
          </DialogHeader>
          {lightboxIndex !== null && (
            <div className="relative mx-4 mb-4 h-[min(70vh,560px)] w-[calc(100%-2rem)] overflow-hidden rounded-md bg-muted">
              <Image
                src={snapshotPhotoUrl(snapshotId, lightboxIndex)}
                alt={`Snapshot photo ${lightboxIndex + 1}`}
                fill
                className="object-contain"
                unoptimized
                sizes="(max-width: 896px) 100vw"
              />
            </div>
          )}
          <div className="flex justify-end gap-2 border-t border-border p-4">
            <Button type="button" variant="outline" onClick={() => setLightboxIndex(null)}>
              <X className="mr-2 h-4 w-4" />
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

export { snapshotPhotoUrl } from '@/lib/snapshotPhotos'
