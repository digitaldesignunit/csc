/**
 * Which paths `proxy.ts` gates by sign-in. The proxy runs for every page path
 * (it issues the CSP nonce, decision 8.164); the gate applies to these
 * prefixes only, the ones its matcher listed before.
 */
export const PROTECTED_PREFIXES = [
  '/components',
  '/dashboard',
  '/admin',
  '/api/backend',
  '/gh-interface',
  '/locate-by-id',
  '/scan',
  '/my-work',
  '/identify',
  '/analytics',
  '/transmit-id',
  '/add-component',
] as const

export function isProtectedPath(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))
}

/** The API routes carry data, not documents: no CSP, no nonce. */
export function isApiPath(pathname: string): boolean {
  return pathname === '/api' || pathname.startsWith('/api/')
}
