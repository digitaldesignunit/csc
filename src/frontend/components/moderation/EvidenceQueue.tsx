'use client'

/**
 * Pending evidence of the datasets the caller moderates (plan P6, spec
 * 7.2 `GET /evidence/pending`): oldest first. Publishing freezes a record
 * and recomputes the folded properties; a reject asks for a reason the
 * author sees. A record of a component that is not published yet waits for
 * it (I26).
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { ExternalLink, FlaskConical } from 'lucide-react'

import EvidenceLifecycleActions from '@/components/moderation/EvidenceLifecycleActions'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { PendingEvidenceItem } from '@/generated'
import { EVIDENCE_METHOD_LABELS, ORIGINAL_FUNCTION_LABELS, VERIFICATION_STATE_LABELS, vocabLabel } from '@/generated/Vocab'
import { loadPending } from '@/lib/evidence/api'
import { quantityLabel } from '@/lib/evidence/format'
import { formatTimestamp } from '@/lib/utils'

export function useEvidenceQueue(enabled: boolean) {
  const [rows, setRows] = useState<PendingEvidenceItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(async () => {
    try {
      setRows(await loadPending())
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the evidence queue')
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => {
    if (enabled) void load()
  }, [enabled, load])
  return { rows, loading, error, load }
}

export default function EvidenceQueue({
  rows,
  loading,
  error,
  onChanged,
}: {
  rows: PendingEvidenceItem[]
  loading: boolean
  error: string | null
  onChanged: () => void
}) {
  return (
    <section className="space-y-3" aria-label="Evidence waiting for moderation">
      <div className="flex items-center gap-2">
        <FlaskConical className="h-5 w-5 text-primary" />
        <h2 className="text-lg font-semibold">Evidence</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Records waiting in the datasets you moderate, oldest first. Publishing freezes a record and
        updates the properties of its component; a rejection goes back to its author with your reason.
      </p>
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">No evidence is waiting for moderation.</CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.id}>
              <Card>
                <CardContent className="space-y-2 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="font-medium">{vocabLabel(EVIDENCE_METHOD_LABELS, row.method)}</span>
                      <span className="text-muted-foreground">{quantityLabel(row.quantity)}</span>
                      {row.catalog_number != null && <Badge variant="secondary">#{row.catalog_number}</Badge>}
                      {row.supersedes && <Badge variant="outline">Correction</Badge>}
                      <Badge variant="outline">{vocabLabel(VERIFICATION_STATE_LABELS, row.verification_state)}</Badge>
                      <span className="text-muted-foreground">
                        {[vocabLabel(ORIGINAL_FUNCTION_LABELS, row.original_function), row.material, row.dataset]
                          .filter(Boolean).join(' / ')}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      <span>
                        {row.recorded_by_username ? `${row.recorded_by_username}, ` : ''}
                        {formatTimestamp(row.created)}
                      </span>
                      <Link href={`/components/${encodeURIComponent(row.identity_id)}`}
                        className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
                        Open <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  </div>
                  {!row.identity_published && (
                    <p className="text-xs text-amber-800 dark:text-amber-200" role="status">
                      Its component is not published yet: publish the waiting version first
                      {row.pending_snapshot_id ? ' (see the moderation queue above)' : ''}.
                    </p>
                  )}
                  <EvidenceLifecycleActions
                    record={{
                      _id: row.id, status: row.status, recorded_by_user_id: '',
                      superseded_by: null, identity_id: row.identity_id,
                    }}
                    dataset={row.dataset}
                    onChanged={onChanged}
                    size="sm"
                  />
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
