import { cn } from '@/lib/utils'

/** Marks a piece that is still in place (decision 8.104). */
export default function InPlaceBadge({ className }: { className?: string }) {
  return (
    <span
      title="Identified in its construction work, not yet deinstalled"
      className={cn(
        'inline-flex shrink-0 items-center rounded-md border border-sky-300 bg-sky-100 px-1.5 py-0.5 text-[10px] font-medium text-sky-900 dark:border-sky-700 dark:bg-sky-950/50 dark:text-sky-100',
        className,
      )}
    >
      In place
    </span>
  )
}
