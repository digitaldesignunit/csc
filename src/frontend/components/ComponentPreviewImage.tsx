// components/ComponentPreviewImage.tsx
import React from 'react'
import Image from 'next/image'

interface ComponentPreviewImageProps {
  comp_id: string
  alt: string
  width: number
  height: number
  maxHeight: number
  className?: string
}

export default function ComponentPreviewImage({
  comp_id,
  alt,
  width,
  height,
  maxHeight,
  className,
}: ComponentPreviewImageProps) {
  const src = `/api/backend/components/${encodeURIComponent(comp_id)}/preview_image`
  const aspectRatio = width / height
  const maxWidth = maxHeight * aspectRatio

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
        // IMPORTANT: let the BROWSER request it (with cookies) – skip server optimizer
        unoptimized
        // optional: better lazy behavior in tables
        loading="lazy"
        sizes={`${width}px`}
      />
    </div>
  )
}
