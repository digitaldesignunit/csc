'use client'

import Link from 'next/link'
import { Clock, History } from 'lucide-react'

import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { Badge } from '@/components/ui/badge'
import { formatTimestamp } from '@/lib/utils'
import SnapshotLifecycleActions from '@/components/moderation/SnapshotLifecycleActions'

type ComponentSnapshotVersionListProps = {
  identityId: string
  snapshots: SnapshotSummaryItem[]
  activeSnapshotId: string
  liveSnapshotId: string
  /** The identity's dataset: decides who sees moderation buttons. */
  dataset?: string | null
}

function versionHref(identityId: string, row: SnapshotSummaryItem): string {
  const base = `/components/${encodeURIComponent(identityId)}`
  if (row.is_current) {
    return base
  }
  const params = new URLSearchParams({ snapshots: row._id })
  return `${base}?${params.toString()}`
}

/**
 * The snapshot versions of one identity, each with its status, the date
 * its state began (valid time) and the lifecycle buttons the caller may use
 * (author: submit / recall / delete; moderator(D): publish / reject /
 * make current / withdraw / reinstate).
 */
export default function ComponentSnapshotVersionList({
  identityId,
  snapshots,
  activeSnapshotId,
  liveSnapshotId,
  dataset,
}: ComponentSnapshotVersionListProps) {
  const hasPendingUpdate = snapshots.some(
    (row) => row.status === 'pending' && !row.is_current,
  )

  if (snapshots.length === 0) {
    return null
  }

  return (
    <section className="border-t border-border pt-3">
      <div className="mb-2 flex items-center gap-2">
        <History className="h-3.5 w-3.5 text-muted-foreground" />
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Snapshot versions
        </h3>
      </div>

      {hasPendingUpdate && activeSnapshotId === liveSnapshotId && (
        <div
          role="status"
          className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
        >
          A newer snapshot is awaiting moderation. The current version shown
          above remains unchanged until it is published.
        </div>
      )}

      <ul className="space-y-2">
        {snapshots.map((row) => {
          const isActive = row._id === activeSnapshotId

          return (
            <li key={row._id}>
              <div
                className={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 text-xs transition-colors ${
                  isActive
                    ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                    : 'border-border bg-muted/20 hover:bg-muted/40'
                }`}
              >
                <Link
                  href={versionHref(identityId, row)}
                  className="flex min-w-0 flex-1 flex-wrap items-center gap-2"
                >
                  <span className="font-medium">v{row.version}</span>
                  {row.is_current && (
                    <Badge variant="default" className="text-[10px]">
                      Current
                    </Badge>
                  )}
                  {isActive && !row.is_current && (
                    <Badge variant="outline" className="text-[10px]">
                      Viewing
                    </Badge>
                  )}
                  {row.status === 'published' ? (
                    <Badge variant="secondary" className="text-[10px]">
                      Published
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="text-[10px] border-amber-400 text-amber-800 dark:text-amber-200"
                    >
                      {row.status}
                    </Badge>
                  )}
                  {row.superseded_by && (
                    <Badge variant="outline" className="text-[10px]">
                      Corrected
                    </Badge>
                  )}
                </Link>

                <div
                  className="flex items-center gap-1 text-xs text-muted-foreground"
                  title="When this state began"
                >
                  <Clock className="h-3 w-3 shrink-0" />
                  <span>since {formatTimestamp(row.effective_from)}</span>
                </div>
                <div className="basis-full empty:hidden">
                  <SnapshotLifecycleActions snapshot={row} dataset={dataset} />
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
