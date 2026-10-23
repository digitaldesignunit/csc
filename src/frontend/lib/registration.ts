/**
 * Who may register without an invitation (decision 8.172): the backend names
 * the open e-mail domains, an empty list means invite only. The domains are
 * not secret. Pure helpers, so the unit test covers them; the fetch and its
 * cache live in hooks/useRegistration.ts.
 */

export type RegistrationInfo = {
  /** Lowercase domains whose addresses register directly (subdomains too); empty = invite only. */
  openDomains: string[]
  inviteOnly: boolean
}

export const REGISTRATION_URL = '/api/backend/auth/registration'

/** The answer of GET /auth/registration, or null when it is not one. */
export function parseRegistration(raw: unknown): RegistrationInfo | null {
  if (typeof raw !== 'object' || raw === null) return null
  // `invite_only` is not read: the domains decide, so no two readers can disagree
  const { open_domains } = raw as { open_domains?: unknown }
  if (!Array.isArray(open_domains) || !open_domains.every((d) => typeof d === 'string')) return null
  const openDomains = (open_domains as string[]).map((d) => d.trim()).filter(Boolean)
  return { openDomains, inviteOnly: openDomains.length === 0 }
}

/** "a.org", "a.org and b.org", "a.org, b.org and c.org". */
export function domainList(domains: readonly string[]): string {
  if (domains.length <= 1) return domains.join('')
  return `${domains.slice(0, -1).join(', ')} and ${domains[domains.length - 1]}`
}

/** The hint under the e-mail field of the open register page. */
export const OPEN_DOMAINS_HINT = 'Registration is open only to addresses of certain domains'

/** What the "?" next to that hint says. */
export function openDomainsHelp(domains: readonly string[]): string {
  const many = domains.length > 1
  return (
    `Addresses of ${many ? 'these domains' : 'this domain'} register directly: ${domainList(domains)} ` +
    '(subdomains included). Every other address needs an invitation code.'
  )
}

/** The label of the invitation code field. */
export function codeFieldLabel(info: RegistrationInfo | null, hasCode: boolean): string {
  if (hasCode || info?.inviteOnly) return 'Invitation code'
  return info ? 'Invitation code (for addresses outside these domains)' : 'Invitation code (optional)'
}

/*
 * While the mode is unknown (the server render, the fetch under way or failed)
 * no text may suggest open registration (8.172 c): the helpers below return
 * null and the caller shows nothing.
 */

/** The "Register" link of the sign-in form and the sidebar: words that fit the mode. */
export function registerLinkText(info: RegistrationInfo | null): string | null {
  if (!info) return null
  return info.inviteOnly ? 'Have an invitation?' : 'Register'
}

/** The small line under "Sign in" in the sidebar. */
export function signInAlternativeText(info: RegistrationInfo | null): string | null {
  if (!info) return null
  return info.inviteOnly ? 'or use an invitation' : 'or register'
}

/** The button of the home page: plain "Sign in" until the mode is known. */
export function signInButtonText(info: RegistrationInfo | null): string {
  return info && !info.inviteOnly ? 'Sign in / Register' : 'Sign in'
}

/** The sentence of the sign-in form in front of that link. */
export function signInRegisterPrompt(info: RegistrationInfo | null): string | null {
  if (!info) return null
  return info.inviteOnly ? 'No account yet?' : "Don't have an account?"
}

/** The line of the admin users page about who may register. */
export function registrationSummary(info: RegistrationInfo | null): string {
  if (!info) return 'Registration outside the open domains works only with an invitation.'
  if (info.inviteOnly) return 'Registration is by invitation only.'
  return (
    `Addresses of ${domainList(info.openDomains)} register without an invitation; ` +
    'registration with any other address works only with an invitation.'
  )
}
