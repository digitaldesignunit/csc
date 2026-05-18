// components/ComponentPreviewImage.tsx
import React from 'react'
import Image from 'next/image'

interface ComponentPreviewImageProps {
  /** Current snapshot id — thumbnail from `GET /snapshots/{snapshot_id}/preview`. */
  snapshot_id: string | null | undefined
  alt: string
  width: number
  height: number
  maxHeight: number
  className?: string
}

export default function ComponentPreviewImage({
  snapshot_id,
  alt,
  width,
  height,
  maxHeight,
  className,
}: ComponentPreviewImageProps) {
  const aspectRatio = width / height
  const maxWidth = maxHeight * aspectRatio

  if (!snapshot_id || snapshot_id.trim().length === 0) {
    return (
      <div
        className={`flex items-center justify-center bg-muted text-[10px] text-muted-foreground ${className ?? ''}`}
        style={{ width, height, maxHeight, maxWidth }}
        aria-hidden
      >
        —
      </div>
    )
  }

  const src = `/api/backend/snapshots/${encodeURIComponent(snapshot_id)}/preview`

  return (
    <div
      className="flex items-center justify-center overflow-hidden"
      style={{ maxHeight, maxWidth }}
    >
      <Image
        src={src}
        alt={alt}
        width={width}
        height={height}
        className={`object-cover ${className ?? ''}`}
        unoptimized
        loading="lazy"
        sizes={`${width}px`}
      />
    </div>
  )
}
