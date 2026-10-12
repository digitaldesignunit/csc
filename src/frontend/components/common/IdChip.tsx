'use client'

/**
 * An id to see and copy (decision 8.141 b): the short id in monospace, the
 * full id on hover, a click copies the full id, and a small menu copies it as
 * a Grasshopper panel that carries the parameter name (`ComponentID`,
 * `SnapshotID`, `RecordID`), so the id can be pasted straight into a
 * definition.
 */
import { useState } from 'react'
import { Check, ChevronDown, Copy, FileText } from 'lucide-react'
import { toast } from 'sonner'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ID_KIND_LABELS, shortId, type IdKind } from '@/lib/ids'
import { cn, generateGrasshopperPanelXML } from '@/lib/utils'

export default function IdChip({
  id,
  kind,
  className,
}: {
  id: string
  kind: IdKind
  className?: string
}) {
  const [copied, setCopied] = useState(false)
  if (!id) return null
  const label = ID_KIND_LABELS[kind]

  const copy = async (text: string, done: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      toast.success(done)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error('Could not copy to the clipboard')
    }
  }

  // inside a link or a card that is itself clickable, the chip must not trigger it
  const quiet = (event: React.SyntheticEvent) => {
    event.stopPropagation()
  }

  return (
    <span
      className={cn(
        'inline-flex items-center overflow-hidden rounded border border-border bg-muted/40 align-middle text-[11px] leading-none',
        className,
      )}
      onClick={quiet}
    >
      <button
        type="button"
        title={`${label}: ${id}. Click to copy.`}
        aria-label={`Copy the ${label.toLowerCase()} ${id}`}
        className="inline-flex items-center gap-1 px-1.5 py-1 font-mono hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        onClick={(event) => {
          event.preventDefault()
          void copy(id, `${label} copied`)
        }}
      >
        {shortId(id)}
        {copied
          ? <Check className="h-3 w-3 text-green-600" aria-hidden />
          : <Copy className="h-3 w-3 text-muted-foreground" aria-hidden />}
      </button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            aria-label={`More ways to copy the ${label.toLowerCase()}`}
            className="border-l border-border px-1 py-1 text-muted-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={(event) => event.preventDefault()}
          >
            <ChevronDown className="h-3 w-3" aria-hidden />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="text-xs">
          <DropdownMenuItem onSelect={() => void copy(id, `${label} copied`)}>
            <Copy className="mr-2 h-3.5 w-3.5" aria-hidden />Copy the id
          </DropdownMenuItem>
          <DropdownMenuItem
            onSelect={() => void copy(generateGrasshopperPanelXML(kind, id), 'Copied as a Grasshopper panel')}
          >
            <FileText className="mr-2 h-3.5 w-3.5" aria-hidden />Copy as Grasshopper panel
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </span>
  )
}
