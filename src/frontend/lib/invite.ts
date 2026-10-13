/**
 * The page /invite (decision 8.144 b): the link in an invitation mail is the
 * same for every recipient. Signed in with the address it names, the account
 * accepts it; signed out, the visitor signs in (and comes back here) or
 * creates an account with the code. Pure helpers, so the unit test covers them.
 */
import type { DatasetRole } from '@/components/admin/RoleCheckboxes'

/** The code of a link: base32 characters (16 are issued), any case; anything else is not one. */
export function inviteCode(value: string | null | undefined): string | null {
  const code = (value ?? '').trim().toUpperCase()
  return /^[A-Z2-7]{8,64}$/.test(code) ? code : null
}

/** Where this page lives for a code: the way back after signing in. */
export function invitePath(code: string): string {
  return `/invite?code=${encodeURIComponent(code)}`
}

/** Sign in, then back to the invitation. */
export function signInHref(code: string): string {
  return `/auth/signin?callbackUrl=${encodeURIComponent(invitePath(code))}`
}

/** Create an account: the registration page fills the code in. */
export function registerHref(code: string): string {
  return `/auth/register?code=${encodeURIComponent(code)}`
}

const ROLE_WORDS: Record<DatasetRole, string> = {
  contributor: 'contributor',
  reviewer: 'reviewer',
  moderator: 'moderator',
}

/** "contributor", "contributor and reviewer", "contributor, reviewer and moderator". */
export function rolesText(roles: readonly string[]): string {
  const words = roles.map((role) => ROLE_WORDS[role as DatasetRole] ?? role)
  if (words.length === 0) return 'member'
  if (words.length === 1) return words[0]
  return `${words.slice(0, -1).join(', ')} and ${words[words.length - 1]}`
}

/** What the invitation offers, in a sentence. */
export function offerText(offer: { dataset_name?: string | null; roles: readonly string[] }): string {
  return offer.dataset_name
    ? `You are invited to the dataset "${offer.dataset_name}" as ${rolesText(offer.roles)}.`
    : 'You are invited to the Catalog of Second Chances.'
}
