'use client'

import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { Clock, History, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatTimestamp } from '@/lib/utils'

type ComponentSnapshotVersionListProps = {
  identityId: string
  snapshots: SnapshotSummaryItem[]
  activeSnapshotId: string
  liveSnapshotId: string
}

function versionHref(identityId: string, row: SnapshotSummaryItem): string {
  const base = `/components/${encodeURIComponent(identityId)}`
  if (row.is_current) {
    return base
  }
  const params = new URLSearchParams({ snapshot_id: row._id })
  return `${base}?${params.toString()}`
}

export default function ComponentSnapshotVersionList({
  identityId,
  snapshots,
  activeSnapshotId,
  liveSnapshotId,
}: ComponentSnapshotVersionListProps) {
  const router = useRouter()
  const { data: session } = useSession()
  const isAdmin = session?.user?.role === 'admin'
  const [rejectingId, setRejectingId] = useState<string | null>(null)

  const hasPendingUpdate = snapshots.some(
    (row) => !row.validated && !row.is_current,
  )

  const handleReject = async (row: SnapshotSummaryItem) => {
    if (row.is_current) {
      toast.error('Use identity delete for the live v0 snapshot.')
      return
    }

    try {
      setRejectingId(row._id)
      const response = await fetch(
        `/api/backend/snapshots/${encodeURIComponent(row._id)}`,
        { method: 'DELETE', credentials: 'include' },
      )
      if (response.ok) {
        toast.success(`Rejected pending v${row.version}`)
        if (activeSnapshotId === row._id) {
          router.push(`/components/${encodeURIComponent(identityId)}`)
        } else {
          router.refresh()
        }
      } else {
        const body = await response.json().catch(() => ({}))
        toast.error(
          typeof body.detail === 'string'
            ? body.detail
            : 'Failed to reject pending snapshot.',
        )
      }
    } catch {
      toast.error('Failed to reject pending snapshot.')
    } finally {
      setRejectingId(null)
    }
  }

  if (snapshots.length === 0) {
    return null
  }

  return (
    <section className="border-t border-border pt-4">
      <div className="mb-3 flex items-center gap-2">
        <History className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Snapshot versions
        </h3>
      </div>

      {hasPendingUpdate && activeSnapshotId === liveSnapshotId && (
        <div
          role="status"
          className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
        >
          A newer snapshot is awaiting admin validation. The live version shown
          above remains unchanged until it is approved.
        </div>
      )}

      <ul className="space-y-2">
        {snapshots.map((row) => {
          const isActive = row._id === activeSnapshotId
          const canReject =
            isAdmin && !row.validated && !row.is_current && row.version > 0

          return (
            <li key={row._id}>
              <div
                className={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm transition-colors ${
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
                      Live
                    </Badge>
                  )}
                  {isActive && !row.is_current && (
                    <Badge variant="outline" className="text-[10px]">
                      Viewing
                    </Badge>
                  )}
                  {row.validated ? (
                    <Badge variant="secondary" className="text-[10px]">
                      Validated
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="text-[10px] border-amber-400 text-amber-800 dark:text-amber-200"
                    >
                      Pending
                    </Badge>
                  )}
                  {row.virtual && (
                    <Badge variant="outline" className="text-[10px]">
                      Virtual
                    </Badge>
                  )}
                </Link>

                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3 shrink-0" />
                    <span>{formatTimestamp(row.created)}</span>
                  </div>
                  {canReject && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-destructive hover:text-destructive"
                      disabled={rejectingId === row._id}
                      onClick={() => void handleReject(row)}
                      aria-label={`Reject pending v${row.version}`}
                    >
                      {rejectingId === row._id ? (
                        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
