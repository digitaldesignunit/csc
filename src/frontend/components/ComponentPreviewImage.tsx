import React from 'react'
import Image from 'next/image'
import { combinePath } from '@/lib/utils'

interface ComponentPreviewImageProps {
  comp_id: string;
  alt: string;
  width: number;
  height: number;
  maxHeight: number;
}

const PreviewBaseURL: string = process.env.NEXT_PUBLIC_COMPONENT_PREVIEW_BASE_URL as string

const ComponentPreviewImage: React.FC<ComponentPreviewImageProps> = ({ comp_id, alt, width, height, maxHeight }) => {
  const src = combinePath(PreviewBaseURL, comp_id, 'webp')
  const aspectRatio = width / height
  const maxWidth = maxHeight * aspectRatio
  return (
    <div className="flex items-center justify-center overflow-hidden" style={{ maxHeight: `${maxHeight}px`, maxWidth: `${maxWidth}px` }}>
      <Image src={src} alt={alt} width={width} height={height} className="object-cover" />
    </div>
  )
}

export default ComponentPreviewImage