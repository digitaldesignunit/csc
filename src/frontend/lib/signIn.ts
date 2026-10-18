/**
 * The web sign-in (decision 8.144 f): the credentials go to the backend's
 * `POST /auth/token` and nowhere else. The backend is the only verifier of
 * the password, so its rate limit sees every attempt, and this server holds no
 * database access. A 401 (wrong credentials) and a 403 (address not verified)
 * both end as a failed sign-in; the answer on the page is the same. A 429
 * (the limit of the address, or of failed sign-ins of the account, 8.162)
 * ends as the `RateLimited` error, which the page words.
 *
 * The log line holds the outcome and never the identifier the visitor typed.
 */

import { RATE_LIMITED } from './signInErrors'

export type AuthorizedUser = {
  id: string
  name?: string
  email?: string
  username: string
  role: string
  apiToken: string
  apiTokenExpiresAt: number
}

export type SignInDeps = {
  fetch: typeof fetch
  backendUrl: string
  /** client header and forwarded address, added to both calls */
  headers: Record<string, string>
  log: (message: string) => void
  now: () => number
}

/** Best-effort decode of the JWT `exp` (seconds) to a ms timestamp. No verification. */
export function decodeJwtExpMs(token: string): number | undefined {
  try {
    const parts = token.split('.')
    if (parts.length < 2) return undefined
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const pad = payloadB64.length % 4
    const padded = pad ? payloadB64 + '='.repeat(4 - pad) : payloadB64
    const payload = JSON.parse(Buffer.from(padded, 'base64').toString('utf8')) as { exp?: number }
    if (typeof payload.exp === 'number') return payload.exp * 1000
  } catch {
    // not a token we can read; the caller falls back
  }
  return undefined
}

type Me = {
  _id?: string
  username?: string
  full_name?: string | null
  email?: string | null
  role?: string
}

export async function signInWithBackend(
  credentials: { identifier?: unknown; password?: unknown } | undefined,
  deps: SignInDeps,
): Promise<AuthorizedUser | null> {
  const { log } = deps
  if (!credentials || typeof credentials.identifier !== 'string' || typeof credentials.password !== 'string') {
    log('[NextAuth][Auth] rejected: no usable credentials')
    return null
  }
  const base = deps.backendUrl.replace(/\/+$/, '')

  const body = new URLSearchParams()
  body.set('username', credentials.identifier.trim())
  body.set('password', credentials.password)

  let resp: Response
  try {
    resp = await deps.fetch(`${base}/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Accept: 'application/json',
        ...deps.headers,
      },
      body,
      cache: 'no-store',
    })
  } catch {
    log('[NextAuth][Auth] backend not reachable')
    return null
  }

  if (!resp.ok) {
    // 401: wrong credentials; 403: address not verified
    log(`[NextAuth][Auth] rejected: backend answered ${resp.status}`)
    // 429: too many attempts for the address or the account; the page says so
    // (an error thrown here reaches the sign-in page as its error code)
    if (resp.status === 429) throw new Error(RATE_LIMITED)
    return null
  }

  let apiToken: string | undefined
  try {
    const tok = (await resp.json()) as { access_token?: string }
    apiToken = typeof tok?.access_token === 'string' ? tok.access_token : undefined
  } catch {
    log('[NextAuth][Auth] token answer not readable')
    return null
  }
  if (!apiToken) {
    log('[NextAuth][Auth] token answer without a token')
    return null
  }

  // the name, address and role NextAuth keeps in its own token
  let me: Me
  try {
    const meResp = await deps.fetch(`${base}/users/me`, {
      headers: { Accept: 'application/json', Authorization: `Bearer ${apiToken}`, ...deps.headers },
      cache: 'no-store',
    })
    if (!meResp.ok) {
      log(`[NextAuth][Auth] rejected: profile answered ${meResp.status}`)
      return null
    }
    me = (await meResp.json()) as Me
  } catch {
    log('[NextAuth][Auth] profile not readable')
    return null
  }
  if (typeof me?._id !== 'string' || typeof me.username !== 'string') {
    log('[NextAuth][Auth] profile without id')
    return null
  }

  log('[NextAuth][Auth] signed in')
  return {
    id: me._id,
    name: me.full_name || me.username,
    email: me.email || undefined,
    username: me.username,
    role: me.role ?? 'user',
    apiToken,
    // the exp claim first, one hour as the last resort
    apiTokenExpiresAt: decodeJwtExpMs(apiToken) ?? deps.now() + 3600 * 1000,
  }
}
