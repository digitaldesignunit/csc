'use client'

import { useCallback, useEffect, useState } from 'react'
import Image from 'next/image'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { Camera, Loader2, Trash2, Upload, X, ZoomIn } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const MAX_PHOTO_SLOTS = 32
const ALLOWED_UPLOAD_TYPES = ['image/jpeg', 'image/png', 'image/webp']

export function snapshotPhotoUrl(snapshotId: string, index: number): string {
  return `/api/backend/snapshots/${encodeURIComponent(snapshotId)}/photos/${index}`
}

async function probePhotoIndex(snapshotId: string, index: number): Promise<boolean> {
  try {
    const res = await fetch(snapshotPhotoUrl(snapshotId, index), {
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
    })
    if (!res.ok) return false
    await res.body?.cancel()
    return true
  } catch {
    return false
  }
}

async function discoverPhotoIndices(
  snapshotId: string,
  hintCount: number,
): Promise<number[]> {
  const scanUpTo = Math.min(
    MAX_PHOTO_SLOTS,
    Math.max(hintCount + 4, hintCount === 0 ? 8 : hintCount + 2),
  )
  const checks = await Promise.all(
    Array.from({ length: scanUpTo }, (_, index) =>
      probePhotoIndex(snapshotId, index).then(exists => (exists ? index : null)),
    ),
  )
  return checks.filter((i): i is number => i !== null)
}

function nextAvailableIndex(indices: number[]): number | null {
  const used = new Set(indices)
  for (let i = 0; i < MAX_PHOTO_SLOTS; i++) {
    if (!used.has(i)) return i
  }
  return null
}

type ComponentSnapshotPhotoGalleryProps = {
  snapshotId: string
  photoCountHint?: number
}

export default function ComponentSnapshotPhotoGallery({
  snapshotId,
  photoCountHint = 0,
}: ComponentSnapshotPhotoGalleryProps) {
  const router = useRouter()
  const { data: session } = useSession()
  const isAdmin = session?.user?.role === 'admin'

  const [indices, setIndices] = useState<number[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [deletingIndex, setDeletingIndex] = useState<number | null>(null)
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

  const handleUpload = async (file: File) => {
    const contentType = (file.type || '').toLowerCase()
    if (!ALLOWED_UPLOAD_TYPES.includes(contentType)) {
      setError('Use JPEG, PNG, or WebP.')
      return
    }

    const slot = nextAvailableIndex(indices)
    if (slot === null) {
      setError(`Maximum of ${MAX_PHOTO_SLOTS} photo slots reached.`)
      return
    }

    setUploading(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('photo', file)
      const res = await fetch(snapshotPhotoUrl(snapshotId, slot), {
        method: 'PUT',
        body: form,
        credentials: 'include',
      })
      if (!res.ok) {
        const body = await res.text().catch(() => '')
        throw new Error(body || `Upload failed (${res.status})`)
      }
      await refreshPhotos()
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (index: number) => {
    if (!window.confirm(`Delete photo ${index + 1}?`)) return

    setDeletingIndex(index)
    setError(null)
    try {
      const res = await fetch(snapshotPhotoUrl(snapshotId, index), {
        method: 'DELETE',
        credentials: 'include',
      })
      if (!res.ok && res.status !== 404) {
        throw new Error(`Delete failed (${res.status})`)
      }
      if (lightboxIndex === index) setLightboxIndex(null)
      await refreshPhotos()
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed.')
    } finally {
      setDeletingIndex(null)
    }
  }

  const onFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (file) void handleUpload(file)
  }

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-3 space-y-0">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Camera className="h-5 w-5" />
              Snapshot photos
            </CardTitle>
            <CardDescription className="mt-1">
              User-uploaded images for the current snapshot state (not the auto-rendered 3D preview).
            </CardDescription>
          </div>
          {isAdmin && (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={uploading || loading}
                className="relative"
                asChild
              >
                <label className="cursor-pointer">
                  {uploading ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4 mr-2" />
                  )}
                  Add photo
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    className="sr-only"
                    onChange={onFileInputChange}
                    disabled={uploading || loading}
                  />
                </label>
              </Button>
            </div>
          )}
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
          ) : indices.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted-foreground">
              No photos for this snapshot yet.
              {isAdmin ? ' Use Add photo to upload one.' : ''}
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
              {indices.map(index => (
                <div
                  key={index}
                  className="group relative aspect-square overflow-hidden rounded-lg border border-border bg-muted"
                >
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
                      sizes="(max-width: 640px) 50vw, 20vw"
                    />
                    <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                      #{index}
                    </span>
                    <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/20 group-hover:opacity-100">
                      <ZoomIn className="h-6 w-6 text-white drop-shadow" />
                    </span>
                  </button>
                  {isAdmin && (
                    <Button
                      type="button"
                      variant="destructive"
                      size="icon"
                      className="absolute top-1 right-1 h-7 w-7 opacity-0 transition group-hover:opacity-100"
                      disabled={deletingIndex === index}
                      onClick={e => {
                        e.stopPropagation()
                        void handleDelete(index)
                      }}
                      aria-label={`Delete photo ${index + 1}`}
                    >
                      {deletingIndex === index ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}

          {!loading && indices.length > 0 && (
            <p className="text-xs text-muted-foreground">
              {indices.length} photo{indices.length === 1 ? '' : 's'} for this snapshot
            </p>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={lightboxIndex !== null}
        onOpenChange={open => {
          if (!open) setLightboxIndex(null)
        }}
      >
        <DialogContent className="max-w-4xl p-0 overflow-hidden">
          <DialogHeader className="p-4 pb-0">
            <DialogTitle>Snapshot photo</DialogTitle>
            <DialogDescription>
              {lightboxIndex !== null ? `Slot #${lightboxIndex}` : ''}
            </DialogDescription>
          </DialogHeader>
          {lightboxIndex !== null && (
            <div className="relative mx-4 mb-4 aspect-[4/3] max-h-[70vh] w-auto overflow-hidden rounded-md bg-muted">
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
              <X className="h-4 w-4 mr-2" />
              Close
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
