'use client'

/**
 * Pending evidence of the datasets the caller moderates (plan P6, spec
 * 7.2 `GET /evidence/pending`): oldest first. Publishing freezes a record
 * and recomputes the folded properties; a reject asks for a reason the
 * author sees (in the card). A record of a component that is not published
 * yet waits for it (I26). One ModerationItemCard each (P11 stage 3).
 */
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Check, Trash2, X } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import type { EvidenceView, PendingEvidenceItem } from '@/generated'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { EVIDENCE_METHOD_LABELS, VERIFICATION_STATE_LABELS, vocabLabel } from '@/generated/Vocab'
import { backendJson } from '@/lib/backend'
import { deleteEvidence, evidenceAction, loadPending } from '@/lib/evidence/api'
import { formatResult, quantityLabel } from '@/lib/evidence/format'
import { useMe } from '@/lib/me'
import { isOwnRecord, submittedLine, type Fact } from '@/lib/moderationCard'
import { formatDay } from '@/lib/utils'
import ModerationItemCard, { type CardAction } from './ModerationItemCard'
import { useDetails } from './useDetails'

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

type Detail = { record: EvidenceView | null; piece: CatalogShallowRow | null }

async function loadDetail(row: PendingEvidenceItem): Promise<Detail> {
  const [record, piece] = await Promise.all([
    backendJson<EvidenceView>(`/evidence/${encodeURIComponent(row.id)}`).catch(() => null),
    backendJson<CatalogShallowRow>(`/identities/${encodeURIComponent(row.identity_id)}`).catch(() => null),
  ])
  return { record, piece }
}

/** The facts of a record that matter for the decision (also used by the Verification tab). */
export function evidenceFacts(row: {
  method: string
  quantity?: string | null
  observed_at: string
}, record: EvidenceView | null): Fact[] {
  const files = (record?.attachments ?? []).filter((a) => !a.removed).length
  return [
    { label: 'Method', value: vocabLabel(EVIDENCE_METHOD_LABELS, row.method) },
    { label: 'Quantity', value: row.quantity ? quantityLabel(row.quantity) : 'Document' },
    { label: 'Result', value: record ? formatResult(record.summary) : '' },
    { label: 'Observed', value: formatDay(row.observed_at) },
    { label: 'Files', value: String(files) },
    {
      label: 'Verification',
      value: vocabLabel(VERIFICATION_STATE_LABELS, record?.verification?.state ?? 'unverified'),
    },
  ].filter((f) => f.value)
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
  const router = useRouter()
  const { me } = useMe()
  const details = useDetails(rows, (row) => row.id, loadDetail)

  const done = (label: string) => {
    toast.success(label)
    onChanged()
    router.refresh()
  }
  const failed = (err: unknown, label: string): never => {
    toast.error(err instanceof Error ? err.message : `${label} failed`)
    throw err
  }

  const actionsOf = (row: PendingEvidenceItem): CardAction[] => [
    {
      key: 'delete', label: 'Delete record', icon: Trash2, kind: 'icon',
      confirm: 'Delete this record? This cannot be undone.',
      run: async () => {
        try { await deleteEvidence(row.id); done('Record deleted') } catch (err) { failed(err, 'Delete') }
      },
    },
    {
      key: 'reject', label: 'Reject', icon: X, kind: 'destructive',
      text: { label: 'Reason (the author sees it)', placeholder: 'Why? The author can turn it back into a draft.', required: true },
      run: async (reason) => {
        try { await evidenceAction(row.id, 'reject', { reason }); done('Rejected') } catch (err) { failed(err, 'Reject') }
      },
    },
    {
      key: 'publish', label: 'Publish', icon: Check, kind: 'primary',
      run: async () => {
        try { await evidenceAction(row.id, 'publish'); done('Published') } catch (err) { failed(err, 'Publish') }
      },
    },
  ]

  return (
    <section className="space-y-3" aria-label="Evidence waiting for moderation">
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="p-4 text-sm text-muted-foreground">No evidence is waiting for moderation.</CardContent>
        </Card>
      ) : (
        <ul className="grid gap-3 xl:grid-cols-2">
          {rows.map((row) => {
            const detail = details[row.id]
            const name = detail?.piece?.name
            return (
              <li key={row.id} className="min-w-0">
                <ModerationItemCard
                  title={`${row.catalog_number != null ? `#${row.catalog_number} ` : ''}${name || row.identity_id}`}
                  sub={vocabLabel(EVIDENCE_METHOD_LABELS, row.method)}
                  chips={[
                    { label: row.supersedes ? 'Correction' : 'Evidence', variant: 'secondary' },
                    ...(row.dataset ? [{ label: row.dataset }] : []),
                    { label: row.status === 'pending' ? 'Pending' : row.status },
                    ...(isOwnRecord(me?.username, row.recorded_by_username) ? [{ label: 'Own record' }] : []),
                  ]}
                  openHref={`/components/${encodeURIComponent(row.identity_id)}`}
                  meta={submittedLine('Submitted', row.recorded_by_username, row.created)}
                  facts={evidenceFacts(row, detail?.record ?? null)}
                  warning={!row.identity_published
                    ? `Its component is not published yet: publish the waiting version first${row.pending_snapshot_id ? ' (see the Snapshots tab)' : ''}.`
                    : null}
                  actions={actionsOf(row)}
                />
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
