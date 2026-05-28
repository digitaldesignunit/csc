'use client'

import { useEffect } from 'react'
import Image from 'next/image'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

export type PhotoLightboxItem = {
  src: string
  alt: string
  caption?: string
}

type PhotoLightboxDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  items: PhotoLightboxItem[]
  index: number | null
  onIndexChange: (index: number) => void
  title?: string
}

export default function PhotoLightboxDialog({
  open,
  onOpenChange,
  items,
  index,
  onIndexChange,
  title = 'Photo preview',
}: PhotoLightboxDialogProps) {
  const current = index !== null && index >= 0 && index < items.length ? items[index] : null
  const canPrev = index !== null && index > 0
  const canNext = index !== null && index < items.length - 1
  const showNav = items.length > 1

  useEffect(() => {
    if (!open || index === null) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' && index > 0) {
        e.preventDefault()
        onIndexChange(index - 1)
      } else if (e.key === 'ArrowRight' && index < items.length - 1) {
        e.preventDefault()
        onIndexChange(index + 1)
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, index, items.length, onIndexChange])

  const close = () => onOpenChange(false)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl overflow-hidden p-0">
        <DialogHeader className="p-4 pb-0">
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {current?.caption ??
              (index !== null && items.length > 0
                ? `${index + 1} of ${items.length}`
                : '')}
          </DialogDescription>
        </DialogHeader>

        {current && (
          <div className="relative mx-4 mb-4 h-[min(70vh,560px)] w-[calc(100%-2rem)] overflow-hidden rounded-md bg-muted">
            {showNav && (
              <>
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className={cn(
                    'absolute left-2 top-1/2 z-10 -translate-y-1/2 rounded-full shadow-md',
                    !canPrev && 'pointer-events-none opacity-40',
                  )}
                  disabled={!canPrev}
                  onClick={() => onIndexChange(index! - 1)}
                  aria-label="Previous photo"
                >
                  <ChevronLeft className="h-5 w-5" />
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="icon"
                  className={cn(
                    'absolute right-2 top-1/2 z-10 -translate-y-1/2 rounded-full shadow-md',
                    !canNext && 'pointer-events-none opacity-40',
                  )}
                  disabled={!canNext}
                  onClick={() => onIndexChange(index! + 1)}
                  aria-label="Next photo"
                >
                  <ChevronRight className="h-5 w-5" />
                </Button>
              </>
            )}

            {current.src.startsWith('blob:') ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={current.src}
                alt={current.alt}
                className="h-full w-full object-contain"
              />
            ) : (
              <Image
                src={current.src}
                alt={current.alt}
                fill
                className="object-contain"
                unoptimized
                sizes="(max-width: 896px) 100vw"
              />
            )}
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border p-4">
          {showNav && index !== null ? (
            <p className="text-xs text-muted-foreground">
              {index + 1} / {items.length}
              {current?.caption ? ` · ${current.caption}` : ''}
            </p>
          ) : (
            <span />
          )}
          <Button type="button" variant="outline" onClick={close}>
            <X className="mr-2 h-4 w-4" />
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
