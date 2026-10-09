/**
 * The pure parts of the Settings "Account" section (plan P11 stage 3, decision
 * 8.118 S6): the rows of the account and the line of a membership.
 */
type MeLike = {
  username: string
  full_name?: string | null
  email?: string | null
  role: string
}

type MembershipLike = {
  dataset: string
  name?: string | null
  roles: string[]
}

export function accountRows(me: MeLike): { label: string; value: string }[] {
  const rows = [{ label: 'Username', value: me.username }]
  if (me.full_name && me.full_name.trim()) rows.push({ label: 'Name', value: me.full_name.trim() })
  rows.push({ label: 'E-mail', value: me.email?.trim() || 'Not stated' })
  if (me.role === 'admin') rows.push({ label: 'Role', value: 'Administrator' })
  return rows
}

/** "ZirKuS: contributor, moderator" (for a screen reader: the badges say the same). */
export function membershipLine(m: MembershipLike): string {
  const roles = m.roles.length ? m.roles.join(', ') : 'no role'
  return `${m.name || m.dataset}: ${roles}`
}
