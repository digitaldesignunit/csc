'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { Camera, Loader2, ZoomIn } from 'lucide-react'

import SnapshotPhotoCapture from '@/components/photos/SnapshotPhotoCapture'
import PhotoCreditLine from '@/components/photos/PhotoCreditLine'
import PhotoLightboxDialog, { type PhotoLightboxItem } from '@/components/photos/PhotoLightboxDialog'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { THUMB_BOX, THUMB_IMG, thumbRow } from '@/lib/photoThumbs'
import {
  fetchSnapshotPhotoIndices,
  parseSnapshotPhotoCount,
  snapshotPhotoUrl,
  type SnapshotPhotoMutationResult,
} from '@/lib/snapshotPhotos'

type ComponentSnapshotPhotoGalleryProps = {
  snapshotId: string
  /** From snapshot.photo_count (passport refreshes from disk). */
  photoCount?: unknown
  compact?: boolean
  /** Without a card of its own: the photos and the lightbox only (the merged
   *  "Photos and location" card, 8.118). */
  embedded?: boolean
  /** Photos can be added only to a version that is not published yet (6.6):
   *  without this the camera and gallery buttons are not shown, admins too. */
  allowUpload?: boolean
  /** The photo credit of the version (8.128 a): a line under the photos and a caption in the lightbox. */
  credit?: unknown
}

export default function ComponentSnapshotPhotoGallery({
  snapshotId,
  photoCount: photoCountRaw,
  compact = false,
  embedded = false,
  allowUpload = true,
  credit,
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

  const rowHeight = embedded ? 'h-24' : 'h-[200px] lg:h-[140px]'
  const gridClass = compact ? thumbRow(indices.length) : 'grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4'

  const thumbClass = compact
    ? THUMB_BOX
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
            compact ? rowHeight : 'py-12'
          }`}
        >
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : isAdmin && allowUpload ? (
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
          dense={embedded}
        />
      ) : indices.length === 0 ? (
        <p
          className={`${
            embedded ? 'py-1' : compact ? `flex ${rowHeight} items-center justify-center` : 'py-8'
          } ${embedded ? 'text-left' : 'text-center'} text-sm text-muted-foreground`}
        >
          No photos yet.
        </p>
      ) : (
        <div className={gridClass}>
          {indices.map((index, position) => (
            <div key={index} className={thumbClass}>
              <button
                type="button"
                className={compact ? 'relative block h-full' : 'relative h-full w-full'}
                onClick={() => setLightboxPosition(position)}
                aria-label={`View photo ${position + 1}`}
              >
                {compact ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={snapshotPhotoUrl(snapshotId, index)}
                    alt={`Snapshot photo ${index + 1}`}
                    className={THUMB_IMG}
                   
                  />
                ) : (
                  <Image
                    src={snapshotPhotoUrl(snapshotId, index)}
                    alt={`Snapshot photo ${index + 1}`}
                    fill
                    className="object-cover transition-opacity group-hover:opacity-90"
                    unoptimized
                    sizes="(max-width: 640px) 50vw, 20vw"
                  />
                )}
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
      {!loading && indices.length > 0 && <PhotoCreditLine credit={credit} className="mt-1.5" />}
    </>
  )

  return (
    <>
      {embedded ? (
        photoBody
      ) : compact ? (
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
        credit={credit}
      />
    </>
  )
}

export { snapshotPhotoUrl } from '@/lib/snapshotPhotos'
