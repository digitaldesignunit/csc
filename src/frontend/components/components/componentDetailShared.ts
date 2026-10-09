import type {
  ComponentIdentity,
  ComponentSnapshot,
  Exit,
} from '@/generated/CatalogModels'
import { EXIT_KIND_LABELS, vocabLabel } from '@/generated/Vocab'
import { formatDay } from '@/lib/utils'

export function conditionLabel(c: number): string {
  switch (c) {
    case 0:
      return '0 --- Unusable as is'
    case 1:
      return '1 --- Poor'
    case 2:
      return '2 --- Average'
    case 3:
      return '3 --- Good'
    default:
      return String(c)
  }
}

export function conditionBadgeClass(c: number): string {
  switch (c) {
    case 0:
      return 'bg-red-500/20 text-red-700 dark:text-red-300'
    case 1:
      return 'bg-orange-500/20 text-orange-700 dark:text-orange-300'
    case 2:
      return 'bg-yellow-500/30 text-yellow-800 dark:text-yellow-200'
    case 3:
      return 'bg-green-500/20 text-green-700 dark:text-green-300'
    default:
      return 'bg-muted/50 text-foreground'
  }
}

export function isNonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.trim().length > 0
}

/** A piece that left circulation (split, installed, recycled, ...; spec 3.1.3). */
export function isOutOfCirculation(row: { exit?: Exit | null }): boolean {
  return row.exit !== undefined && row.exit !== null
}

/**
 * A piece still in place: identified in its construction work, not yet
 * deinstalled (`origin.planned`, decision 8.104). It is in circulation.
 */
export function isInPlace(row: {
  exit?: Exit | null
  origin?: { planned?: boolean | null } | null
}): boolean {
  return row.origin?.planned === true && !isOutOfCirculation(row)
}

/**
 * The batch line of a component (decision 8.105): "Batch: 10 recorded, 3
 * drawn, 7 remaining"; null when it is not a batch. `remaining` is derived
 * by the backend, so the drawn count is what is left of the recorded size.
 */
export function batchLine(
  identity: { remaining?: number | null },
  snapshot: { quantity?: number | null },
): string | null {
  const remaining = identity.remaining
  const recorded = snapshot.quantity ?? 1
  if (remaining === null || remaining === undefined || recorded <= 1) return null
  return `Batch: ${recorded} recorded, ${recorded - remaining} drawn, ${remaining} remaining`
}

/** A date as precisely as it is known: "2019", "05.2019", "12.05.2019". */
export function formatDateAtPrecision(value: string, precision?: string | null): string {
  const [y, m, d] = value.slice(0, 10).split('-')
  if (precision === 'year') return y
  if (precision === 'month') return `${m}.${y}`
  if (precision === 'unknown') return `${d}.${m}.${y} (uncertain)`
  if (precision === 'day' || /T00:00:00/.test(value)) return `${d}.${m}.${y}`
  return formatDay(value)
}

/** "Split (29.04.2026)" --- the exit kind and date, for badges and banners. */
export function exitSummary(exit: Exit | null | undefined): string {
  if (!exit) return ''
  const kind = vocabLabel(EXIT_KIND_LABELS, exit.kind)
  const at = exit.at ? formatDateAtPrecision(String(exit.at), exit.at_precision) : ''
  return at ? `${kind} (${at})` : kind
}

/**
 * True when frame, class or proxy of the snapshot could not be derived
 * (decision 8.60): what it shows is that of an earlier geometry. The stamps
 * only say `failed`; the text stays with the dataset's maintainers.
 */
export function geometryFailed(snapshot: { derivation?: unknown }): boolean {
  const stamps = (snapshot.derivation ?? {}) as Record<string, { error?: string | null } | null>
  return ['frame', 'shape_class', 'proxies'].some((stage) => !!stamps[stage]?.error)
}

/** Published is the only status listed by default (spec 3.3.3). */
export function isPublished(snapshot: { status?: string | null }): boolean {
  return snapshot.status === 'published'
}

export function parentIdentityIds(identity: ComponentIdentity): string[] {
  const ids = identity.parent_identities
  if (!Array.isArray(ids)) {
    return []
  }
  return ids.map((id) => String(id).trim()).filter((id) => id.length > 0)
}

export function snapshotDisplayName(snapshot: ComponentSnapshot): string {
  return typeof snapshot.name === 'string' && snapshot.name.trim().length > 0
    ? snapshot.name
    : 'Unnamed component'
}

/** Display name for who added the snapshot (username only; never expose user ids). */
export function snapshotAddedByDisplay(
  snapshot: Pick<ComponentSnapshot, 'added_by_username'>,
): string | null {
  return isNonEmptyString(snapshot.added_by_username)
    ? snapshot.added_by_username.trim()
    : null
}

/**
 * Whether the piece is reserved. `reserved` holds the reserving user's id, which
 * an anonymous caller never receives (decision 8.101); `is_reserved` is the
 * status for everyone, on every identity the backend serves.
 */
export function isReserved(identity: Pick<ComponentIdentity, 'is_reserved'>): boolean {
  return identity.is_reserved === true
}

export interface ExtendedUser {
  id?: string
  sub?: string
  username?: string | null
  name?: string | null
  email?: string | null
}
