/**
 * Response headers of the web app (decision 8.144 g), sent for every path by
 * `headers()` in next.config.ts. The Content-Security-Policy is not here: it
 * carries a nonce per request and is built in `proxy.ts` (lib/csp.ts, decision
 * 8.164), `frame-ancestors 'none'` among its directives.
 */

/** The canonical host: HSTS is sent there only, never on the legacy host
 *  (which redirects) or on a local address. No `includeSubDomains`: other
 *  sub-domains of the host are not under this app's control. */
export const CANONICAL_HOST = '2ndchances.build'

export const HSTS = 'max-age=31536000'

/** Sent on every response. */
export const SECURITY_HEADERS: ReadonlyArray<{ key: string; value: string }> = [
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'X-Content-Type-Options', value: 'nosniff' },
]

export type HeaderRule = {
  source: string
  has?: Array<{ type: 'host'; value: string }>
  headers: Array<{ key: string; value: string }>
}

export function headerRules(): HeaderRule[] {
  return [
    { source: '/:path*', headers: SECURITY_HEADERS.map((h) => ({ ...h })) },
    {
      source: '/:path*',
      has: [{ type: 'host', value: CANONICAL_HOST }],
      headers: [{ key: 'Strict-Transport-Security', value: HSTS }],
    },
  ]
}
