/**
 * Access tokens in the interface (decision 8.167): what the backend answers
 * and the small rules the pages need. The backend decides everything (who may
 * hold a token, the limit of 10, expiry, revoke); this only shapes the text.
 * Pure, so the unit test covers it.
 */
export type AccessTokenRow = {
  id: string
  kind: string
  name: string
  scopes: string[]
  short_id: string
  created: string
  expires: string
  last_used?: string | null
  revoked?: string | null
  status: 'active' | 'expired' | 'revoked'
  renew_due: boolean
}

/** The answer of a create or a renew: the only time the token is sent. */
export type AccessTokenCreated = AccessTokenRow & { token: string }

export type AdminAccessTokenRow = AccessTokenRow & {
  owner_id: string
  owner_username?: string | null
}

export type AccessTokenOptions = {
  can_create: boolean
  lifetimes: number[]
  default_days: number
  max_active: number
}

export const TOKEN_PREFIX: Record<string, string> = { pat: 'csc_pat_', device: 'csc_dev_' }

/** "1 year", "90 days": the choice of the lifetime. */
export function lifetimeLabel(days: number): string {
  return days === 365 ? '1 year' : `${days} days`
}

/** What the list shows of a token: the prefix, the first 8 characters, dots. */
export function tokenPreview(row: Pick<AccessTokenRow, 'kind' | 'short_id'>): string {
  return `${TOKEN_PREFIX[row.kind] ?? 'csc_'}${row.short_id}...`
}

export const SCOPE_LABELS: Record<string, string> = {
  'read:catalog': 'Read the catalog (MCP)',
  'gh:client': 'Grasshopper client',
}

export function scopeText(scopes: string[]): string {
  return scopes.map((scope) => SCOPE_LABELS[scope] ?? scope).join(', ')
}

/** "Renew" is offered within 14 days of the expiry and after it; never for a revoked token. */
export function canRenew(row: Pick<AccessTokenRow, 'status' | 'renew_due' | 'kind'>): boolean {
  return row.kind === 'pat' && (row.status === 'expired' || (row.status === 'active' && row.renew_due))
}

/** A token that can still be revoked. */
export function canRevoke(row: Pick<AccessTokenRow, 'status'>): boolean {
  return row.status !== 'revoked'
}

export const ONCE_NOTE =
  'Copy this token now. You will not see it again; if you lose it, revoke it and create a new one.'

/** The text of the 409 and 403 of a create, as the backend words them; anything else: a general one. */
export function createFailure(error: unknown): string {
  const message = error instanceof Error ? error.message : ''
  return message && !/^Request failed/.test(message) ? message : 'The token could not be created.'
}
