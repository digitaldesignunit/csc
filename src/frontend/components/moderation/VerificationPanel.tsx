'use client'

/**
 * Verification of one evidence record (spec 3.3.3, decision 8.12): the
 * recorder's own `self_attested` claim, and the four-eyes `reviewed` /
 * `accredited` of a reviewer(D) or admin who is neither the recorder nor a
 * performer. A reviewer steps a state back only to `unverified` (8.70 a).
 * The reviewer sees the accreditation block of every performer and a link
 * to the accreditation body's public register; the backend checks I22,
 * I27 and the note again.
 */
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { ExternalLink, ShieldCheck } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { Accreditation, Actor } from '@/generated'
import type { EvidenceView } from '@/generated'
import { VERIFICATION_STATE_LABELS, vocabLabel } from '@/generated/Vocab'
import { putVerification } from '@/lib/evidence/api'
import { VERIFICATION_NOTES, verificationClass } from '@/lib/evidence/format'
import { useMe } from '@/lib/me'
import { formatDay } from '@/lib/utils'

const DAKKS_ID = /^D-[A-Z]{2}-\d{5}-\d{2}-\d{2}$/

/**
 * Where a reviewer checks an accreditation. DAkkS publishes the certificate
 * of an accredited body under its registration number, so a typed-in id of
 * that shape links straight to the certificate; its search page takes no id
 * in the address, and neither does NANDO (notified bodies), so for those the
 * link is the entry page of the register (decision 8.83).
 */
function registerLink(
  scheme: string,
  id: string | null | undefined,
): { label: string; url: string } | null {
  if (scheme === 'iso_17025') {
    const exact = (id ?? '').trim()
    return DAKKS_ID.test(exact)
      ? {
        label: `DAkkS certificate ${exact}`,
        url: `https://www.dakks.de/files/data/as/pdf/${encodeURIComponent(exact)}.pdf`,
      }
      : { label: 'DAkkS register of accredited bodies (search it)', url: 'https://www.dakks.de/de/akkreditierte-stellen-suche.html' }
  }
  if (scheme === 'notified_body') {
    return {
      label: 'NANDO database of notified bodies (search the number)',
      url: 'https://webgate.ec.europa.eu/single-market-compliance-space/#/notified-bodies',
    }
  }
  return null
}

function AccreditationNote({ actor }: { actor: Actor }) {
  const accreditation = actor.accreditation as Accreditation | null | undefined
  if (!accreditation) return null
  const register = registerLink(String(accreditation.scheme), accreditation.id)
  return (
    <li className="rounded-md border border-border p-2 text-xs">
      <p className="font-medium">{actor.organization || actor.name || 'Performer'}</p>
      <p className="text-muted-foreground">
        {String(accreditation.scheme)}: {accreditation.id}
        {accreditation.body ? `, ${accreditation.body}` : ''}
        {accreditation.valid_until ? `, valid until ${accreditation.valid_until}` : ''}
      </p>
      {accreditation.scope && accreditation.scope.length > 0 && (
        <p className="text-muted-foreground">Scope: {accreditation.scope.join(', ')}</p>
      )}
      {register && (
        <a href={register.url} target="_blank" rel="noopener noreferrer"
          className="mt-1 inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
          {register.label}<ExternalLink className="h-3 w-3" />
        </a>
      )}
    </li>
  )
}

export default function VerificationPanel({
  record,
  dataset,
  onChanged,
}: {
  record: EvidenceView
  dataset: string | null | undefined
  onChanged?: () => void
}) {
  const router = useRouter()
  const { me, isAdmin, rolesIn } = useMe()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const state = record.verification?.state ?? 'unverified'
  const performers = (record.performed_by ?? []) as Actor[]
  const accredited = performers.filter((a) => a.accreditation)

  const isRecorder = !!me && record.recorded_by_user_id === me._id
  const isPerformer = !!me && performers.some((a) => a.user_id === me._id)
  const soft = state === 'unverified' || state === 'self_attested'
  const canSelfAttest = isRecorder && isPerformer && soft
  const reviewerRole = isAdmin || rolesIn(dataset).includes('reviewer')
  const canReview = reviewerRole && !isRecorder && !isPerformer
  const reviewable = ['reviewed', 'accredited', 'unverified'].filter((s) => s !== state)

  const set = async (next: string, withNote?: string) => {
    setBusy(true)
    try {
      await putVerification(record._id, next, withNote || null)
      toast.success(`Verification: ${vocabLabel(VERIFICATION_STATE_LABELS, next)}`)
      setNote('')
      onChanged?.()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not set the verification')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className={`text-[10px] ${verificationClass(state)}`}>
          <ShieldCheck className="mr-1 h-3 w-3" />{vocabLabel(VERIFICATION_STATE_LABELS, state)}
        </Badge>
        <span className="text-xs text-muted-foreground">{VERIFICATION_NOTES[state]}</span>
      </div>
      {record.verification?.at && (
        <p className="text-xs text-muted-foreground">
          {record.verification.by?.name || record.verification.by?.organization
            || (state === 'self_attested' ? record.recorded_by_username : null)
            || (state === 'reviewed' || state === 'accredited' ? 'A reviewer' : 'Someone')}, {formatDay(record.verification.at)}
          {record.verification.note ? `: ${record.verification.note}` : ''}
        </p>
      )}

      {canSelfAttest && (
        <Button size="sm" variant="outline" className="h-8 text-xs" disabled={busy}
          onClick={() => void set(state === 'self_attested' ? 'unverified' : 'self_attested')}>
          {state === 'self_attested' ? 'Withdraw my attestation' : 'I performed this and stand by the result'}
        </Button>
      )}

      {canReview && (
        <div className="space-y-2 rounded-md border border-border p-2">
          <p className="text-xs font-medium">Review (a second person)</p>
          {accredited.length > 0 && (
            <ul className="space-y-1">{accredited.map((a, i) => <AccreditationNote key={i} actor={a} />)}</ul>
          )}
          <Textarea
            rows={2}
            value={note}
            placeholder="What did you check? Needed for accredited."
            aria-label="What you checked"
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="flex flex-wrap gap-1.5">
            {reviewable.map((target) => (
              <Button key={target} size="sm" variant={target === 'unverified' ? 'ghost' : 'outline'}
                className="h-8 text-xs" disabled={busy || (target === 'accredited' && !note.trim())}
                onClick={() => void set(target, note.trim())}>
                {target === 'unverified' ? 'Step back to unverified' : `Mark ${vocabLabel(VERIFICATION_STATE_LABELS, target).toLowerCase()}`}
              </Button>
            ))}
          </div>
        </div>
      )}
      {reviewerRole && !canReview && state !== 'reviewed' && state !== 'accredited' && (isRecorder || isPerformer) && (
        <p className="text-xs text-muted-foreground">
          You recorded or performed this: a second person has to review it.
        </p>
      )}
    </div>
  )
}
