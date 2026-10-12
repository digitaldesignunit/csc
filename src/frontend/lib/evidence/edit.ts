/**
 * Editing a record of evidence before it is published (decision 8.127): who
 * may, and the request body of `PATCH /evidence/{id}` built from the form.
 */
import type { EvidenceBulkItem } from '@/generated'
import type { MethodInfo } from '@/lib/evidence/api'

/**
 * The rule of `PATCH /evidence/{id}` (evidence_lifecycle.py): a draft is
 * edited by its author or `moderator(D)`, a pending record by `moderator(D)`;
 * a rejected, published or withdrawn one is not edited here (a rejected one
 * goes back to a draft first, a published one is corrected).
 */
export function canEditEvidence(status: string, isAuthor: boolean, isModerator: boolean): boolean {
  if (status === 'draft') return isAuthor || isModerator
  if (status === 'pending') return isModerator
  return false
}

/**
 * The body of the PATCH: the create body of the form without what the route
 * refuses (the component, and `self_attested`, which only a new record
 * sets). A value the form left empty is sent as `null` so that the edit can
 * clear it; a missing key would keep the stored value.
 */
export function editBody(item: EvidenceBulkItem, method: MethodInfo): Record<string, unknown> {
  const body: Record<string, unknown> = { ...(item as unknown as Record<string, unknown>) }
  delete body.identity_id
  delete body.self_attested
  body.notes = body.notes ?? null
  if (method.summary_from_client) body.summary = body.summary ?? null
  return body
}

type VerifiedRecord = {
  recorded_by_user_id?: string | null
  verification?: { state?: string | null } | null
}

/**
 * What an edit does to the verification of the record, to say before saving
 * (decision 8.127 note b; the rule of `PATCH /evidence/{id}`): a
 * self-attested record whose recorder is no longer among the performers
 * becomes unverified, and a reviewed or accredited record becomes
 * unverified when the result changes. Empty when the edit leaves it alone.
 */
export function verificationNotices(record: VerifiedRecord, performerUserIds: string[]): string[] {
  const state = record.verification?.state ?? 'unverified'
  const notices: string[] = []
  if (state === 'self_attested' && !performerUserIds.includes(record.recorded_by_user_id ?? '')) {
    notices.push(
      'This record is self-attested by its recorder. The recorder is no longer among the performers, so '
      + 'saving resets the verification to unverified.',
    )
  }
  if (state === 'reviewed' || state === 'accredited') {
    notices.push(
      `This record is ${state}. If you change its result, saving resets the verification to unverified; `
      + 'a reviewer has to confirm it again.',
    )
  }
  return notices
}
