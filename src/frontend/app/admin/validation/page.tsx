'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ExternalLink, Inbox } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import SnapshotLifecycleActions from '@/components/moderation/SnapshotLifecycleActions'
import EvidenceQueue, { useEvidenceQueue } from '@/components/moderation/EvidenceQueue'
import type { PendingSnapshotItem } from '@/generated/SnapshotModels'
import { ORIGINAL_FUNCTION_LABELS, vocabLabel } from '@/generated/Vocab'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'
import { formatTimestamp } from '@/lib/utils'

function pendingSnapshotHref(row: PendingSnapshotItem): string {
  const params = new URLSearchParams({ snapshots: row._id })
  return `/components/${encodeURIComponent(row.identity_id)}?${params.toString()}`
}

/**
 * Moderation queue (plan P3): pending snapshots of the datasets the caller
 * moderates (admin: all), oldest first. Publish makes the snapshot current;
 * reject asks for a reason the author sees.
 */
export default function ModerationQueuePage() {
  const router = useRouter()
  const { me, loading: meLoading, moderatesAny } = useMe()
  const [pending, setPending] = useState<PendingSnapshotItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const evidenceQueue = useEvidenceQueue(moderatesAny)

  useEffect(() => {
    if (!meLoading && me && !moderatesAny) router.push('/')
  }, [me, meLoading, moderatesAny, router])

  const load = useCallback(async () => {
    try {
      setPending(await backendJson<PendingSnapshotItem[]>('/snapshots/pending'))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the queue')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (moderatesAny) void load()
  }, [moderatesAny, load])

  return (
    <div className="container mx-auto max-w-4xl space-y-4 p-6">
      <div className="flex items-center gap-2">
        <Inbox className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold sm:text-2xl">Moderation queue</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Snapshots and evidence waiting in the datasets you moderate, oldest first.
        Publishing makes a snapshot the component&apos;s current state; a rejection goes
        back to its author with your reason.
      </p>

      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : pending.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Nothing is waiting for moderation.
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {pending.map((row) => (
            <li key={row._id}>
              <Card>
                <CardContent className="space-y-2 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="font-medium">{row.name || row.identity_id}</span>
                      <Badge variant="outline">v{row.version}</Badge>
                      {row.catalog_number != null && (
                        <Badge variant="secondary">#{row.catalog_number}</Badge>
                      )}
                      {row.supersedes && <Badge variant="outline">Correction</Badge>}
                      <span className="text-muted-foreground">
                        {[vocabLabel(ORIGINAL_FUNCTION_LABELS, row.original_function),
                          row.material, row.dataset]
                          .filter(Boolean)
                          .join(' / ')}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>
                        {row.added_by_username ? `${row.added_by_username}, ` : ''}
                        {formatTimestamp(row.created)}
                      </span>
                      <Link
                        href={pendingSnapshotHref(row)}
                        className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                      >
                        Open <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                  <SnapshotLifecycleActions
                    snapshot={{ _id: row._id, version: row.version, status: row.status, is_current: row.is_current }}
                    dataset={row.dataset}
                    onChanged={() => void load()}
                    size="sm"
                  />
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <div className="pt-4">
        <EvidenceQueue
          rows={evidenceQueue.rows}
          loading={evidenceQueue.loading}
          error={evidenceQueue.error}
          onChanged={() => { void load(); void evidenceQueue.load() }}
        />
      </div>
    </div>
  )
}
