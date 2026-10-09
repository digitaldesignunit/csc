/**
 * The photo credit of a version (decision 8.128 a): one small muted line, the
 * link as an external link. It renders nothing without a credit.
 */
import { ExternalLink } from 'lucide-react'

import { creditDisplayText, creditToShow } from '@/lib/photoCredit'
import { cn } from '@/lib/utils'

export default function PhotoCreditLine({ credit, className }: { credit: unknown; className?: string }) {
  const shown = creditToShow(credit)
  if (!shown) return null
  const text = creditDisplayText(shown.text)
  return (
    <p className={cn('text-xs text-muted-foreground', className)}>
      {shown.url ? (
        <a href={shown.url} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-1 underline underline-offset-2 hover:text-foreground">
          {text}
          <ExternalLink className="h-3 w-3 shrink-0" aria-hidden />
          <span className="sr-only">(opens the source in a new tab)</span>
        </a>
      ) : text}
    </p>
  )
}
