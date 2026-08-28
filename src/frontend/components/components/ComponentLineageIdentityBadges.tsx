import Link from 'next/link'

type LineageStatus = 'active' | 'consumed' | null

type LineageIdentity = {
  id: string
  status: LineageStatus
}

type ComponentLineageIdentityBadgesProps = {
  identities: LineageIdentity[]
  kind: 'parent' | 'child'
}

const statusBadgeClass: Record<Exclude<LineageStatus, null>, string> = {
  consumed:
    'border-amber-300 bg-amber-100 text-amber-800 hover:bg-amber-200/80 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200 dark:hover:bg-amber-900/50',
  active:
    'border-green-300 bg-green-100 text-green-800 hover:bg-green-200/80 dark:border-green-700 dark:bg-green-950/40 dark:text-green-200 dark:hover:bg-green-900/50',
}

const unknownBadgeClass =
  'border-border bg-muted/50 text-foreground hover:bg-muted dark:bg-muted/40'

export default function ComponentLineageIdentityBadges({
  identities,
  kind,
}: ComponentLineageIdentityBadgesProps) {
  if (identities.length === 0) {
    return <span className="text-xs italic text-muted-foreground">None</span>
  }

  return (
    <ul className="flex max-w-full flex-wrap items-center justify-end gap-1">
      {identities.map((item) => {
        const statusClass =
          item.status === 'consumed' || item.status === 'active'
            ? statusBadgeClass[item.status]
            : unknownBadgeClass
        const statusLetter =
          item.status === 'consumed' ? 'C' : item.status === 'active' ? 'A' : null
        const statusLabel =
          item.status === 'consumed'
            ? 'consumed'
            : item.status === 'active'
              ? 'active'
              : 'status unknown'
        return (
          <li key={item.id} className="min-w-0 max-w-full">
            <Link
              href={`/components/${encodeURIComponent(item.id)}`}
              title={`Open ${kind} ${item.id} (${statusLabel})`}
              className={`inline-flex max-w-full items-center gap-1 rounded-md border py-0.5 pl-0.5 pr-1.5 ${statusClass}`}
            >
              {statusLetter ? (
                <span
                  aria-hidden="true"
                  className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] bg-black/10 font-sans text-[9px] font-bold leading-none dark:bg-white/15"
                >
                  {statusLetter}
                </span>
              ) : null}
              <span className="min-w-0 font-mono text-[10px] font-medium break-all">{item.id}</span>
            </Link>
          </li>
        )
      })}
    </ul>
  )
}
