'use client'

/**
 * The "?" next to a field (decision 7.1): opens on tap and on hover or
 * focus, built on the Popover (the Tooltip does not open on touch). The
 * text is the backend's field description, rendered as plain text.
 */
import { useRef, useState } from 'react'
import { CircleHelp } from 'lucide-react'

import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

export default function Help({ text, label }: { text: string; label: string }) {
  const [open, setOpen] = useState(false)
  const closeTimer = useRef<number | null>(null)
  const hoverOpenedAt = useRef(0)
  if (!text) return null

  const hover = (next: boolean) => {
    if (closeTimer.current) window.clearTimeout(closeTimer.current)
    if (next) {
      if (!open) hoverOpenedAt.current = Date.now()
      setOpen(true)
    } else closeTimer.current = window.setTimeout(() => setOpen(false), 120)
  }

  // A tap fires the emulated mouseenter (opens) and then the click: the click
  // must not toggle the popover shut again.
  const click = (event: React.MouseEvent) => {
    event.preventDefault()
    if (Date.now() - hoverOpenedAt.current < 600) return
    setOpen((value) => !value)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Help: ${label}`}
          className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={click}
          onMouseEnter={() => hover(true)}
          onMouseLeave={() => hover(false)}
        >
          <CircleHelp className="h-4 w-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        className="w-72 max-w-[calc(100vw-2rem)] p-3 text-xs leading-relaxed"
        onMouseEnter={() => hover(true)}
        onMouseLeave={() => hover(false)}
      >
        <p className="font-medium">{label}</p>
        <p className="mt-1 whitespace-pre-line text-muted-foreground">{text}</p>
      </PopoverContent>
    </Popover>
  )
}
