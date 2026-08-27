'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { Camera, Loader2, ZoomIn } from 'lucide-react'

import SnapshotPhotoCapture from '@/components/photos/SnapshotPhotoCapture'
import PhotoLightboxDialog, { type PhotoLightboxItem } from '@/components/photos/PhotoLightboxDialog'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  fetchSnapshotPhotoIndices,
  parseSnapshotPhotoCount,
  snapshotPhotoUrl,
  type SnapshotPhotoMutationResult,
} from '@/lib/snapshotPhotos'

type ComponentSnapshotPhotoGalleryProps = {
  snapshotId: string
  /** From snapshot.photo_count (compose refreshes from disk). */
  photoCount?: unknown
  compact?: boolean
}

export default function ComponentSnapshotPhotoGallery({
  snapshotId,
  photoCount: photoCountRaw,
  compact = false,
}: ComponentSnapshotPhotoGalleryProps) {
  const photoCountFromProps = parseSnapshotPhotoCount(photoCountRaw)
  const router = useRouter()
  const { data: session } = useSession()
  const isAdmin = session?.user?.role === 'admin'

  const [knownPhotoCount, setKnownPhotoCount] = useState<number | null>(photoCountFromProps)
  const [indices, setIndices] = useState<number[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lightboxPosition, setLightboxPosition] = useState<number | null>(null)

  useEffect(() => {
    setKnownPhotoCount(photoCountFromProps)
  }, [photoCountFromProps])

  const refreshPhotos = useCallback(
    async (opts?: { afterMutation?: boolean; photoCountHint?: number | null }) => {
      if (!snapshotId) {
        setIndices([])
        setLoading(false)
        return
      }
      setLoading(true)
      setError(null)
      try {
        const countForFetch =
          opts?.photoCountHint ??
          (opts?.afterMutation ? null : knownPhotoCount ?? photoCountFromProps)

        const found = await fetchSnapshotPhotoIndices(snapshotId, countForFetch)
        setIndices(found)
        if (opts?.photoCountHint !== undefined && opts.photoCountHint !== null) {
          setKnownPhotoCount(opts.photoCountHint)
        } else {
          setKnownPhotoCount(found.length)
        }
      } catch {
        setError('Failed to load photos.')
        setIndices([])
      } finally {
        setLoading(false)
      }
    },
    [snapshotId, knownPhotoCount, photoCountFromProps],
  )

  useEffect(() => {
    if (photoCountFromProps === 0) {
      setIndices([])
      setKnownPhotoCount(0)
      setLoading(false)
      return
    }
    void refreshPhotos()
  }, [photoCountFromProps, refreshPhotos, snapshotId])

  const lightboxItems = useMemo<PhotoLightboxItem[]>(
    () =>
      indices.map(index => ({
        src: snapshotPhotoUrl(snapshotId, index),
        alt: `Snapshot photo slot ${index}`,
        caption: `Slot #${index}`,
      })),
    [indices, snapshotId],
  )

  useEffect(() => {
    if (lightboxPosition === null) return
    if (lightboxItems.length === 0) {
      setLightboxPosition(null)
      return
    }
    if (lightboxPosition >= lightboxItems.length) {
      setLightboxPosition(lightboxItems.length - 1)
    }
  }, [lightboxItems.length, lightboxPosition])

  const gridClass = compact
    ? 'flex h-[200px] lg:h-[140px] gap-1.5 overflow-hidden'
    : 'grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4'

  const thumbClass = compact
    ? 'group relative h-full min-w-0 flex-1 overflow-hidden rounded-md border border-border bg-muted'
    : 'group relative aspect-square overflow-hidden rounded-lg border border-border bg-muted'

  const photoBody = (
    <>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <div
          className={`flex items-center justify-center text-muted-foreground ${
            compact ? 'h-[200px] lg:h-[140px]' : 'py-12'
          }`}
        >
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : isAdmin ? (
        <SnapshotPhotoCapture
          mode="live"
          snapshotId={snapshotId}
          indices={indices}
          onChange={async (result?: SnapshotPhotoMutationResult) => {
            await refreshPhotos({
              afterMutation: true,
              photoCountHint: result?.photoCount,
            })
            router.refresh()
          }}
          compact={compact}
        />
      ) : indices.length === 0 ? (
        <p
          className={`${
            compact ? 'flex h-[200px] lg:h-[140px] items-center justify-center' : 'py-8'
          } text-center text-sm text-muted-foreground`}
        >
          No photos for this snapshot yet.
        </p>
      ) : (
        <div className={gridClass}>
          {indices.map((index, position) => (
            <div key={index} className={thumbClass}>
              <button
                type="button"
                className="relative h-full w-full"
                onClick={() => setLightboxPosition(position)}
                aria-label={`View photo ${position + 1}`}
              >
                <Image
                  src={snapshotPhotoUrl(snapshotId, index)}
                  alt={`Snapshot photo ${index + 1}`}
                  fill
                  className="object-cover transition-opacity group-hover:opacity-90"
                  unoptimized
                  sizes={compact ? '140px' : '(max-width: 640px) 50vw, 20vw'}
                />
                <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                  #{index}
                </span>
                <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/20 group-hover:opacity-100">
                  <ZoomIn className="h-5 w-5 text-white drop-shadow" />
                </span>
              </button>
            </div>
          ))}
        </div>
      )}
    </>
  )

  return (
    <>
      {compact ? (
        <section className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-foreground">
            <Camera className="h-4 w-4" />
            Snapshot photos
            {!loading && indices.length > 0 && (
              <span className="font-normal text-xs text-muted-foreground">
                {indices.length}
              </span>
            )}
          </h3>
          {photoBody}
        </section>
      ) : (
        <Card>
          <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0 py-4">
            <div className="flex flex-col gap-0">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Camera className="h-4 w-4 shrink-0" />
                Snapshot photos
              </CardTitle>
              <CardDescription className="mt-1">
                User-uploaded images for the current snapshot (not the 3D preview).
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">{photoBody}</CardContent>
        </Card>
      )}

      <PhotoLightboxDialog
        open={lightboxPosition !== null}
        onOpenChange={open => {
          if (!open) setLightboxPosition(null)
        }}
        items={lightboxItems}
        index={lightboxPosition}
        onIndexChange={setLightboxPosition}
        title="Snapshot photo"
      />
    </>
  )
}

export { snapshotPhotoUrl } from '@/lib/snapshotPhotos'
