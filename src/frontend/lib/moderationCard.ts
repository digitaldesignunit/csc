/**
 * The pure parts of the moderation cards (plan P11 stage 3, decision 8.118):
 * what a card of the Snapshots, Evidence and Verification tabs says, in one
 * shape: kind chip, "submitted by ... waiting ...", the key facts, and what a
 * correction changes.
 */
import { ORIGINAL_FUNCTION_LABELS, SHAPE_CLASS_LABELS, vocabLabel } from '@/generated/Vocab'
import { sizeLabel } from '@/lib/browse'
import { formatDay } from '@/lib/utils'

export type Fact = { label: string; value: string }

const DAY = 86_400_000

/** "waiting 3 days", "waiting 1 day", "waiting since today". */
export function waitingLabel(since: string | null | undefined, now: number = Date.now()): string {
  const start = since ? Date.parse(since) : NaN
  if (Number.isNaN(start)) return ''
  const days = Math.floor((now - start) / DAY)
  if (days < 1) return 'waiting since today'
  return days === 1 ? 'waiting 1 day' : `waiting ${days} days`
}

/** "Submitted by dev-contrib on 07.10.2026, waiting 3 days". */
export function submittedLine(
  verb: string,
  user: string | null | undefined,
  created: string | null | undefined,
  now: number = Date.now(),
): string {
  const who = user ? ` by ${user}` : ''
  const when = created ? ` on ${formatDay(created)}` : ''
  const waiting = waitingLabel(created, now)
  return `${verb}${who}${when}${waiting ? `, ${waiting}` : ''}`
}

/** The viewer submitted it themselves: a moderator may publish their own record from the queue (8.120), marked "Own record". */
export function isOwnRecord(viewer: string | null | undefined, author: string | null | undefined): boolean {
  return !!viewer && !!author && viewer === author
}

export type SnapshotKind = 'New piece' | 'New state' | 'Correction' | 'Cut' | 'Draw'

/** What a waiting version is: a first state, a later one, a correction, or a piece cut or drawn from others. */
export function snapshotKind(input: {
  version: number
  supersedes?: string | null
  parents: number
  drawn: boolean
}): SnapshotKind {
  if (input.supersedes) return 'Correction'
  if (input.version === 0 && input.parents > 0) return input.drawn ? 'Draw' : 'Cut'
  return input.version === 0 ? 'New piece' : 'New state'
}

export type SnapshotLike = {
  name?: string | null
  bbx?: number[] | null
  shape_class?: string | null
  quantity?: number | null
  fragment?: boolean | null
  color?: number[] | null
  notes?: string | null
  capture?: { method?: string | null } | null
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null)

/** What a correction changes against the version it replaces, one short phrase each. */
export function snapshotChanges(previous: SnapshotLike | null | undefined, current: SnapshotLike | null | undefined): string[] {
  if (!previous || !current) return []
  const out: string[] = []
  if ((previous.name ?? '') !== (current.name ?? '')) out.push(`name "${previous.name ?? ''}" to "${current.name ?? ''}"`)
  if (!same(previous.bbx?.map(Math.round), current.bbx?.map(Math.round))) {
    out.push(`size ${sizeLabel(previous.bbx) || 'none'} to ${sizeLabel(current.bbx) || 'none'} mm`)
  }
  if ((previous.quantity ?? 1) !== (current.quantity ?? 1)) out.push(`quantity ${previous.quantity ?? 1} to ${current.quantity ?? 1}`)
  if (!same(previous.color, current.color)) out.push('colour')
  if ((previous.notes ?? '') !== (current.notes ?? '')) out.push('notes')
  if (Boolean(previous.fragment) !== Boolean(current.fragment)) out.push('fragment flag')
  if ((previous.shape_class ?? '') !== (current.shape_class ?? '')) {
    out.push(`shape class ${vocabLabel(SHAPE_CLASS_LABELS, previous.shape_class)} to ${vocabLabel(SHAPE_CLASS_LABELS, current.shape_class)}`)
  }
  return out
}

const CAPTURE_LABELS: Record<string, string> = {
  photogrammetry: 'Photogrammetry',
  lidar: 'Lidar',
  structured_light: 'Structured light',
  manual: 'Manual',
}

/** The facts a moderator decides on, for a waiting snapshot. */
export function snapshotFacts(
  row: { original_function?: string | null; material?: string | null },
  snapshot: SnapshotLike | null,
  changes: string[],
): Fact[] {
  const facts: Fact[] = [
    { label: 'Function', value: row.original_function ? vocabLabel(ORIGINAL_FUNCTION_LABELS, row.original_function) : '' },
    { label: 'Material', value: row.material ?? '' },
  ]
  if (snapshot) {
    const size = sizeLabel(snapshot.bbx)
    facts.push({ label: 'Size', value: size ? `${size} mm` : '' })
    facts.push({ label: 'Shape class', value: snapshot.shape_class ? vocabLabel(SHAPE_CLASS_LABELS, snapshot.shape_class) : '' })
    const method = snapshot.capture?.method
    facts.push({ label: 'Capture', value: method ? (CAPTURE_LABELS[method] ?? method) : 'Authored' })
    if ((snapshot.quantity ?? 1) > 1) facts.push({ label: 'Quantity', value: String(snapshot.quantity) })
  }
  if (changes.length) facts.push({ label: 'Changes', value: changes.join(String.fromCharCode(10)) })
  return facts.filter((f) => f.value)
}

/** A long note cut at a word, with whether there is more. */
export function truncateNote(text: string, max = 140): { text: string; more: boolean } {
  const clean = text.trim()
  if (clean.length <= max) return { text: clean, more: false }
  const cut = clean.slice(0, max)
  const space = cut.lastIndexOf(' ')
  return { text: `${(space > max * 0.6 ? cut.slice(0, space) : cut).trimEnd()}...`, more: true }
}
