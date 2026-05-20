'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Image from 'next/image'
import { Camera, ImagePlus, Loader2, Trash2, ZoomIn } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  ALLOWED_PHOTO_TYPES,
  MAX_PHOTO_SLOTS,
  deleteSnapshotPhoto,
  nextAvailablePhotoIndex,
  snapshotPhotoUrl,
  uploadSnapshotPhoto,
} from '@/lib/snapshotPhotos'

type StagedItem = {
  id: string
  file: File
  previewUrl: string
}

type SnapshotPhotoCaptureStagedProps = {
  mode: 'staged'
  files: File[]
  onFilesChange: (files: File[]) => void
  maxPhotos?: number
  disabled?: boolean
}

type SnapshotPhotoCaptureLiveProps = {
  mode: 'live'
  snapshotId: string
  indices: number[]
  onChange: () => void | Promise<void>
  maxPhotos?: number
  disabled?: boolean
  compact?: boolean
}

export type SnapshotPhotoCaptureProps =
  | SnapshotPhotoCaptureStagedProps
  | SnapshotPhotoCaptureLiveProps

function isAllowedPhotoFile(file: File): boolean {
  const contentType = (file.type || '').toLowerCase()
  return ALLOWED_PHOTO_TYPES.includes(contentType as (typeof ALLOWED_PHOTO_TYPES)[number])
}

export default function SnapshotPhotoCapture(props: SnapshotPhotoCaptureProps) {
  const maxPhotos = props.maxPhotos ?? MAX_PHOTO_SLOTS
  const disabled = props.disabled ?? false
  const compact = props.mode === 'live' ? (props.compact ?? false) : false

  const cameraInputRef = useRef<HTMLInputElement>(null)
  const galleryInputRef = useRef<HTMLInputElement>(null)

  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null)
  const [stagedItems, setStagedItems] = useState<StagedItem[]>([])

  const stagedFiles = props.mode === 'staged' ? props.files : []

  useEffect(() => {
    if (props.mode !== 'staged') return

    const next: StagedItem[] = stagedFiles.map(file => ({
      id: `${file.name}-${file.size}-${file.lastModified}`,
      file,
      previewUrl: URL.createObjectURL(file),
    }))

    setStagedItems(prev => {
      prev.forEach(item => URL.revokeObjectURL(item.previewUrl))
      return next
    })

    return () => {
      next.forEach(item => URL.revokeObjectURL(item.previewUrl))
    }
  }, [props.mode, stagedFiles])

  const count = props.mode === 'staged' ? stagedFiles.length : props.indices.length
  const atLimit = count >= maxPhotos

  const addStagedFiles = useCallback(
    (incoming: FileList | File[]) => {
      if (props.mode !== 'staged' || disabled) return

      const list = Array.from(incoming)
      const valid = list.filter(isAllowedPhotoFile)
      if (valid.length === 0) {
        setError('Use JPEG, PNG, or WebP.')
        return
      }

      const room = maxPhotos - props.files.length
      if (room <= 0) {
        setError(`Maximum of ${maxPhotos} photos.`)
        return
      }

      const accepted = valid.slice(0, room)
      if (valid.length > accepted.length) {
        setError(`Only ${room} more photo${room === 1 ? '' : 's'} allowed.`)
      } else {
        setError(null)
      }

      props.onFilesChange([...props.files, ...accepted])
    },
    [disabled, maxPhotos, props],
  )

  const removeStagedAt = useCallback(
    (index: number) => {
      if (props.mode !== 'staged') return
      const next = props.files.filter((_, i) => i !== index)
      props.onFilesChange(next)
      setError(null)
    },
    [props],
  )

  const addLiveFiles = useCallback(
    async (incoming: FileList | File[]) => {
      if (props.mode !== 'live' || disabled) return

      setBusy(true)
      setError(null)
      try {
        const valid = Array.from(incoming).filter(isAllowedPhotoFile)
        if (valid.length === 0) {
          setError('Use JPEG, PNG, or WebP.')
          return
        }

        const used = new Set(props.indices)
        for (const file of valid) {
          if (used.size >= maxPhotos) {
            setError(`Maximum of ${maxPhotos} photos.`)
            break
          }
          const slot = nextAvailablePhotoIndex(used)
          if (slot === null) break
          await uploadSnapshotPhoto(props.snapshotId, slot, file)
          used.add(slot)
        }
        await props.onChange()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Upload failed.')
      } finally {
        setBusy(false)
        if (cameraInputRef.current) cameraInputRef.current.value = ''
        if (galleryInputRef.current) galleryInputRef.current.value = ''
      }
    },
    [disabled, maxPhotos, props],
  )

  const confirmDeleteLivePhoto = useCallback(async () => {
    const index = pendingDeleteIndex
    if (index === null || props.mode !== 'live' || disabled) return

    setPendingDeleteIndex(null)
    setBusy(true)
    setError(null)
    try {
      await deleteSnapshotPhoto(props.snapshotId, index)
      await props.onChange()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed.')
    } finally {
      setBusy(false)
    }
  }, [disabled, pendingDeleteIndex, props])

  const onCameraChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (props.mode === 'staged') addStagedFiles([file])
    else void addLiveFiles([file])
  }

  const onGalleryChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files
    e.target.value = ''
    if (!list?.length) return
    if (props.mode === 'staged') addStagedFiles(list)
    else void addLiveFiles(list)
  }

  const gridClass = compact
    ? 'flex flex-wrap gap-2'
    : 'grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4'

  const thumbClass = compact
    ? 'group relative size-16 shrink-0 overflow-hidden rounded-md border border-border bg-muted sm:size-[4.5rem]'
    : 'group relative aspect-square overflow-hidden rounded-lg border border-border bg-muted'

  const liveTiles = useMemo(() => {
    if (props.mode !== 'live') return []
    return props.indices.map(index => ({
      index,
      src: snapshotPhotoUrl(props.snapshotId, index),
    }))
  }, [props])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="default"
          size="sm"
          disabled={disabled || busy || atLimit}
          onClick={() => cameraInputRef.current?.click()}
        >
          {busy ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Camera className="mr-2 h-4 w-4" />
          )}
          Take photo
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled || busy || atLimit}
          onClick={() => galleryInputRef.current?.click()}
        >
          <ImagePlus className="mr-2 h-4 w-4" />
          Add from gallery
        </Button>
      </div>

      <input
        ref={cameraInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture="environment"
        className="sr-only"
        onChange={onCameraChange}
        disabled={disabled || busy || atLimit}
        aria-hidden
      />
      <input
        ref={galleryInputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        multiple
        className="sr-only"
        onChange={onGalleryChange}
        disabled={disabled || busy || atLimit}
        aria-hidden
      />

      <p className="text-xs text-muted-foreground">
        On mobile, &quot;Take photo&quot; opens the camera. Up to {maxPhotos} images (JPEG, PNG, or
        WebP).
      </p>

      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}

      {props.mode === 'staged' && stagedItems.length === 0 && (
        <p className="py-6 text-center text-sm text-muted-foreground">No photos added yet.</p>
      )}

      {props.mode === 'live' && liveTiles.length === 0 && !busy && (
        <p className="py-6 text-center text-sm text-muted-foreground">No photos for this snapshot yet.</p>
      )}

      {(props.mode === 'staged' ? stagedItems.length > 0 : liveTiles.length > 0) && (
        <div className={gridClass}>
          {props.mode === 'staged'
            ? stagedItems.map((item, index) => (
                <div key={item.id} className={thumbClass}>
                  <button
                    type="button"
                    className="relative h-full w-full"
                    onClick={() => setLightboxSrc(item.previewUrl)}
                    aria-label={`Preview photo ${index + 1}`}
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={item.previewUrl}
                      alt={`Staged photo ${index + 1}`}
                      className="h-full w-full object-cover"
                    />
                  </button>
                  <Button
                    type="button"
                    variant="destructive"
                    size="icon"
                    className="absolute right-1 top-1 h-7 w-7"
                    disabled={disabled || busy}
                    onClick={() => removeStagedAt(index)}
                    aria-label={`Remove photo ${index + 1}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))
            : liveTiles.map(({ index, src }) => (
                <div key={index} className={thumbClass}>
                  <button
                    type="button"
                    className="relative h-full w-full"
                    onClick={() => setLightboxSrc(src)}
                    aria-label={`View photo ${index + 1}`}
                  >
                    <Image
                      src={src}
                      alt={`Snapshot photo ${index + 1}`}
                      fill
                      className="object-cover"
                      unoptimized
                      sizes={compact ? '72px' : '20vw'}
                    />
                    <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-white">
                      #{index}
                    </span>
                    <span className="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition group-hover:bg-black/20 group-hover:opacity-100">
                      <ZoomIn className="h-6 w-6 text-white drop-shadow" />
                    </span>
                  </button>
                  <Button
                    type="button"
                    variant="destructive"
                    size="icon"
                    className="absolute right-1 top-1 h-7 w-7 opacity-100 sm:opacity-0 sm:transition sm:group-hover:opacity-100"
                    disabled={disabled || busy}
                    onClick={() => setPendingDeleteIndex(index)}
                    aria-label={`Delete photo ${index + 1}`}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
        </div>
      )}

      {count > 0 && (
        <p className="text-xs text-muted-foreground">
          {count} photo{count === 1 ? '' : 's'}
          {props.mode === 'staged' ? ' ready to upload' : ' on this snapshot'}
        </p>
      )}

      <AlertDialog
        open={pendingDeleteIndex !== null}
        onOpenChange={open => {
          if (!open) setPendingDeleteIndex(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete photo?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDeleteIndex !== null
                ? `Photo #${pendingDeleteIndex} will be removed from this snapshot. This cannot be undone.`
                : 'This photo will be removed from this snapshot.'}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={busy}
              onClick={() => void confirmDeleteLivePhoto()}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={lightboxSrc !== null} onOpenChange={open => !open && setLightboxSrc(null)}>
        <DialogContent className="max-w-4xl overflow-hidden p-0">
          <DialogHeader className="p-4 pb-0">
            <DialogTitle>Photo preview</DialogTitle>
            <DialogDescription>User-uploaded snapshot image</DialogDescription>
          </DialogHeader>
          {lightboxSrc && (
            <div className="relative mx-4 mb-4 h-[min(70vh,560px)] w-[calc(100%-2rem)] overflow-hidden rounded-md bg-muted">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={lightboxSrc} alt="Preview" className="h-full w-full object-contain" />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
