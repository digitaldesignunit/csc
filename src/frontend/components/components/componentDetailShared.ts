import type { CatalogComponent, ComponentIdentity } from '@/generated/CatalogModels'
import type { CatalogShallowRow } from '@/generated/catalogExtras'

export function conditionLabel(c: number): string {
  switch (c) {
    case 0:
      return '0 — Destroyed / Retired'
    case 1:
      return '1 — Poor'
    case 2:
      return '2 — Average'
    case 3:
      return '3 — Good'
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

export function isConsumedShallowRow(row: Pick<CatalogShallowRow, 'consumed_at'>): boolean {
  return (
    row.consumed_at !== undefined &&
    row.consumed_at !== null &&
    String(row.consumed_at).trim() !== ''
  )
}

export function primaryParentIdentityId(identity: ComponentIdentity): string | undefined {
  const ids = identity.parent_identities
  if (Array.isArray(ids) && ids.length > 0) {
    return String(ids[0])
  }
  return undefined
}

export function snapshotDisplayName(snapshot: CatalogComponent['snapshot']): string {
  return typeof snapshot.name === 'string' && snapshot.name.trim().length > 0
    ? snapshot.name
    : 'Unnamed component'
}

/** Display name for who added the snapshot (username only; never expose user ids). */
export function snapshotAddedByDisplay(
  snapshot: Pick<CatalogComponent['snapshot'], 'added_by_username'>,
): string | null {
  return isNonEmptyString(snapshot.added_by_username)
    ? snapshot.added_by_username.trim()
    : null
}

export interface ExtendedUser {
  id?: string
  sub?: string
  username?: string | null
  name?: string | null
  email?: string | null
}
