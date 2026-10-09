import { cn } from '@/lib/utils'
import type { Chip, ChipTone } from '@/lib/componentDetail'

export const CHIP_TONE: Record<ChipTone, string> = {
  neutral: 'border-border bg-muted text-foreground',
  good: 'border-green-300 bg-green-100 text-green-800 dark:border-green-700 dark:bg-green-950/50 dark:text-green-200',
  info: 'border-sky-300 bg-sky-100 text-sky-900 dark:border-sky-700 dark:bg-sky-950/50 dark:text-sky-100',
  warn: 'border-amber-300 bg-amber-100 text-amber-900 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100',
  bad: 'border-red-300 bg-red-100 text-red-900 dark:border-red-700 dark:bg-red-950/50 dark:text-red-100',
}

/** A small status chip: the tone says how it matters, the title explains it. */
export default function ChipView({ chip, href, className }: { chip: Chip; href?: string; className?: string }) {
  const classes = cn('inline-flex items-center rounded-md border px-2 py-0.5 text-[11px] font-medium', CHIP_TONE[chip.tone], className)
  return href ? (
    <a href={href} title={chip.title} className={cn(classes, 'hover:underline')}>{chip.label}</a>
  ) : (
    <span title={chip.title} className={classes}>{chip.label}</span>
  )
}
