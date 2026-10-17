/**
 * The error code the sign-in hands to the sign-in page when the backend
 * counted too many attempts (a 429: the limit of the address, or the limit of
 * failed sign-ins of the account, decision 8.162), and the words for it. Kept
 * apart from `signIn.ts` (server only) so the page can import it.
 */
export const RATE_LIMITED = 'RateLimited'

export const RATE_LIMITED_TEXT =
  'Too many sign-in attempts. Wait a few minutes and try again, or reset your password.'
