'use client'

/**
 * The records a second person can review (plan P6, decision 8.12; P11 stage
 * 3), listed for the Moderation page's Verification tab: one
 * ModerationItemCard each, with Mark reviewed as the decision and Mark
 * accredited (which needs a note, asked in the card) beside it. The queue
 * already leaves out what the caller recorded or performed.
 */
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { BadgeCheck, ShieldCheck } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import type { Accreditation, Actor } from '@/generated'
import { EVIDENCE_METHOD_LABELS, VERIFICATION_STATE_LABELS, vocabLabel } from '@/generated/Vocab'
import { putVerification } from '@/lib/evidence/api'
import { formatResult, quantityLabel } from '@/lib/evidence/format'
import { submittedLine, type Fact } from '@/lib/moderationCard'
import type { VerificationRow } from '@/lib/moderationQueues'
import { formatDay } from '@/lib/utils'
import ModerationItemCard, { type CardAction } from './ModerationItemCard'

function performedBy(record: VerificationRow['record']): string {
  return ((record.performed_by ?? []) as Actor[])
    .map((actor) => {
      const name = actor.organization || actor.name || ''
      const accreditation = actor.accreditation as Accreditation | null | undefined
      return accreditation ? `${name || 'Performer'} (${String(accreditation.scheme)} ${accreditation.id})` : name
    })
    .filter(Boolean)
    .join(', ')
}

function factsOf(record: VerificationRow['record']): Fact[] {
  const state = record.verification?.state ?? 'unverified'
  return [
    { label: 'Method', value: vocabLabel(EVIDENCE_METHOD_LABELS, record.method) },
    { label: 'Quantity', value: record.summary?.quantity ? quantityLabel(String(record.summary.quantity)) : 'Document' },
    { label: 'Result', value: formatResult(record.summary) },
    { label: 'Observed', value: formatDay(record.observed_at) },
    { label: 'Recorder', value: record.recorded_by_username ?? '' },
    { label: 'Verification', value: vocabLabel(VERIFICATION_STATE_LABELS, state) },
    { label: 'Performed by', value: performedBy(record) },
  ].filter((f) => f.value)
}

export default function VerificationQueue({
  rows,
  loading,
  error,
  onChanged,
}: {
  rows: VerificationRow[]
  loading: boolean
  error: string | null
  onChanged: () => void
}) {
  const router = useRouter()

  const mark = async (id: string, state: 'reviewed' | 'accredited', note: string) => {
    try {
      await putVerification(id, state, note || null)
      toast.success(`Verification: ${vocabLabel(VERIFICATION_STATE_LABELS, state)}`)
      onChanged()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not set the verification')
      throw err
    }
  }

  const actionsOf = (record: VerificationRow['record']): CardAction[] => {
    const state = record.verification?.state ?? 'unverified'
    const actions: CardAction[] = []
    if (state !== 'accredited') {
      actions.push({
        key: 'accredited', label: 'Mark accredited', icon: BadgeCheck, kind: 'outline',
        text: { label: 'What did you check? (needed for accredited)', placeholder: 'The accreditation, the scope, the report.', required: true },
        run: (note) => mark(record._id, 'accredited', note),
      })
    }
    if (state !== 'reviewed' && state !== 'accredited') {
      actions.push({
        key: 'reviewed', label: 'Mark reviewed', icon: ShieldCheck, kind: 'primary',
        run: () => mark(record._id, 'reviewed', ''),
      })
    }
    return actions
  }

  return (
    <section className="space-y-3" aria-label="Records waiting for a review">
      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : rows.length === 0 ? (
        <Card><CardContent className="p-4 text-sm text-muted-foreground">Nothing is waiting for a review.</CardContent></Card>
      ) : (
        <ul className="grid gap-3 xl:grid-cols-2">
          {rows.map(({ record, piece }) => (
            <li key={record._id} className="min-w-0">
              <ModerationItemCard
                title={`${piece?.catalog_number != null ? `#${piece.catalog_number} ` : ''}${piece?.name || record.identity_id}`}
                sub={vocabLabel(EVIDENCE_METHOD_LABELS, record.method)}
                chips={[
                  { label: 'Evidence', variant: 'secondary' },
                  ...(piece?.dataset ? [{ label: piece.dataset }] : []),
                  { label: record.status === 'pending' ? 'Pending' : record.status },
                ]}
                openHref={`/components/${encodeURIComponent(record.identity_id)}`}
                meta={submittedLine('Recorded', record.recorded_by_username, record.created)}
                facts={factsOf(record)}
                note={record.notes}
                actions={actionsOf(record)}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
