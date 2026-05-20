'use client'

import { useEffect, useState } from 'react'
import Image from 'next/image'
import { ImageOff } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ComponentPreviewImageProps {
  /** Current snapshot id — thumbnail from `GET /snapshots/{snapshot_id}/preview`. */
  snapshot_id: string | null | undefined
  alt: string
  width: number
  height: number
  maxHeight: number
  className?: string
}

function PreviewPlaceholder({
  width,
  height,
  maxHeight,
  className,
}: Pick<
  ComponentPreviewImageProps,
  'width' | 'height' | 'maxHeight' | 'className'
>) {
  const aspectRatio = width / height
  const maxWidth = maxHeight * aspectRatio

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-0.5 bg-white text-muted-foreground',
        className,
      )}
      style={{ width, height, maxHeight, maxWidth }}
      role="img"
      aria-label="No preview available"
    >
      <ImageOff className="size-3.5 shrink-0 opacity-70" aria-hidden />
      <span className="text-[9px] leading-none opacity-70">No preview</span>
    </div>
  )
}

export default function ComponentPreviewImage({
  snapshot_id,
  alt,
  width,
  height,
  maxHeight,
  className,
}: ComponentPreviewImageProps) {
  const [loadFailed, setLoadFailed] = useState(false)
  const aspectRatio = width / height
  const maxWidth = maxHeight * aspectRatio

  useEffect(() => {
    setLoadFailed(false)
  }, [snapshot_id])

  if (!snapshot_id || snapshot_id.trim().length === 0 || loadFailed) {
    return (
      <PreviewPlaceholder
        width={width}
        height={height}
        maxHeight={maxHeight}
        className={className}
      />
    )
  }

  const src = `/api/backend/snapshots/${encodeURIComponent(snapshot_id)}/preview`

  return (
    <div
      className={cn(
        'relative overflow-hidden bg-white',
        className,
      )}
      style={{ width, height, maxHeight, maxWidth }}
    >
      <Image
        src={src}
        alt={alt}
        fill
        className="object-contain"
        unoptimized
        loading="lazy"
        sizes={`${width}px`}
        onError={() => setLoadFailed(true)}
      />
    </div>
  )
}
