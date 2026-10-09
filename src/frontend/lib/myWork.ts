/**
 * The pure parts of "My work" (plan P11 stage 2, decision 8.118 Q4): the
 * caller's own unfinished records --- snapshots and evidence together --- with
 * their status and, for a rejected one, the reason; the lines of "Waiting for
 * you"; the bulk submit of own drafts (decision 8.127).
 */
import { EVIDENCE_METHOD_LABELS, vocabLabel } from '@/generated/Vocab'
import type { MySnapshotItem } from '@/generated/SnapshotModels'

export type Piece = { name?: string | null; catalog_number?: number | null; dataset?: string | null }

type EvidenceLike = {
  _id: string
  identity_id: string
  method: string
  status: string
  created: string
  status_changed_at?: string | null
  status_history?: { to: string; reason?: string | null }[]
}

export type MyRecord = {
  kind: 'snapshot' | 'evidence'
  id: string
  identityId: string
  /** "Snapshot v2", "Evidence: Rebound hammer" */
  title: string
  /** "#12 Beam 07" */
  piece: string
  dataset: string
  status: string
  /** when the status last changed (or the record was created) */
  at: string
  reason: string
  href: string
}

export function pieceLabel(piece: Piece | null | undefined): string {
  if (!piece) return ''
  const number = piece.catalog_number != null ? `#${piece.catalog_number}` : ''
  const name = (piece.name ?? '').trim()
  return [number, name].filter(Boolean).join(' ')
}

export function rejectionReason(history: { to: string; reason?: string | null }[] | undefined): string {
  for (const entry of [...(history ?? [])].reverse()) {
    if (entry.to === 'rejected') return (entry.reason ?? '').trim()
  }
  return ''
}

/** Own snapshots and evidence in one list, the most recently changed first. */
export function mergeMyRecords(
  snapshots: MySnapshotItem[],
  evidence: EvidenceLike[],
  pieces: Map<string, Piece | null>,
): MyRecord[] {
  const rows: MyRecord[] = []
  for (const s of snapshots) {
    const piece = pieces.get(s.identity_id)
    rows.push({
      kind: 'snapshot',
      id: s._id,
      identityId: s.identity_id,
      title: `Snapshot v${s.version}`,
      piece: pieceLabel(piece ?? { name: s.name, catalog_number: s.catalog_number }),
      dataset: s.dataset ?? piece?.dataset ?? '',
      status: s.status,
      at: s.status_changed_at ?? s.created,
      reason: s.rejection_reason ?? '',
      href: `/components/${encodeURIComponent(s.identity_id)}?snapshots=${encodeURIComponent(s._id)}`,
    })
  }
  for (const e of evidence) {
    const piece = pieces.get(e.identity_id)
    rows.push({
      kind: 'evidence',
      id: e._id,
      identityId: e.identity_id,
      title: `Evidence: ${vocabLabel(EVIDENCE_METHOD_LABELS, e.method)}`,
      piece: pieceLabel(piece),
      dataset: piece?.dataset ?? '',
      status: e.status,
      at: e.status_changed_at ?? e.created,
      reason: e.status === 'rejected' ? rejectionReason(e.status_history) : '',
      href: `/components/${encodeURIComponent(e.identity_id)}`,
    })
  }
  return rows.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : a.id < b.id ? -1 : 1))
}

// BULK SUBMIT (decision 8.127) -------------------------------------------------
/** One key per record (a snapshot and a record of evidence may share an id). */
export const recordKey = (row: Pick<MyRecord, 'kind' | 'id'>): string => `${row.kind}:${row.id}`

/** Only a draft is submitted; pending, rejected and published records are not. */
export const isSubmittable = (row: Pick<MyRecord, 'status'>): boolean => row.status === 'draft'

/** The keys of every record that can be submitted. */
export function submittableKeys(rows: MyRecord[]): string[] {
  return rows.filter(isSubmittable).map(recordKey)
}

export type SubmitResult = {
  key: string
  /** "Snapshot v2", "Evidence: Rebound hammer" */
  title: string
  piece: string
  ok: boolean
  /** the new status, or the reason the server gave */
  message: string
}

/**
 * Submits the chosen records one after the other and says for each what
 * happened. A refused record does not stop the others. `submitOne` throws
 * when the server refuses; it returns the new status.
 */
export async function submitRecords(
  rows: MyRecord[],
  chosen: ReadonlySet<string>,
  submitOne: (row: MyRecord) => Promise<string>,
): Promise<SubmitResult[]> {
  const results: SubmitResult[] = []
  for (const row of rows) {
    const key = recordKey(row)
    if (!chosen.has(key) || !isSubmittable(row)) continue
    const base = { key, title: row.title, piece: row.piece }
    try {
      results.push({ ...base, ok: true, message: await submitOne(row) })
    } catch (err) {
      results.push({ ...base, ok: false, message: err instanceof Error ? err.message : 'Submit failed' })
    }
  }
  return results
}

/** The lines of "Waiting for you": only those with something waiting. */
export function waitingLines(counts: {
  snapshots: number
  evidence: number
  verification: number
}): { key: 'snapshots' | 'evidence' | 'verification'; text: string; tab: string }[] {
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  const out: { key: 'snapshots' | 'evidence' | 'verification'; text: string; tab: string }[] = []
  if (counts.snapshots > 0) {
    out.push({ key: 'snapshots', text: `${plural(counts.snapshots, 'version', 'versions')} to moderate`, tab: 'snapshots' })
  }
  if (counts.evidence > 0) {
    out.push({ key: 'evidence', text: `${plural(counts.evidence, 'record', 'records')} to moderate`, tab: 'evidence' })
  }
  if (counts.verification > 0) {
    out.push({ key: 'verification', text: `${plural(counts.verification, 'record', 'records')} to verify`, tab: 'verification' })
  }
  return out
}
