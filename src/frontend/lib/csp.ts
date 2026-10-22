/**
 * The Content-Security-Policy of the web app (decision 8.164, completing the
 * headers of 8.144 g). `proxy.ts` builds one policy per request, with a fresh
 * nonce, and sends it as the only CSP header; Next puts the nonce on its own
 * scripts and `app/layout.tsx` hands it to next-themes.
 *
 * The Location Map (decision 8.171) loads its map tiles from one host, which
 * is the only addition: `img-src` also allows `MAP_TILE_ORIGIN`.
 *
 * Scripts: the nonce, `'strict-dynamic'` (the scripts Next loads from a
 * nonced script run), and `'wasm-unsafe-eval'` for the meshopt decoder that
 * drei's `useGLTF` always sets up. Styles stay `'unsafe-inline'` (sonner,
 * Radix, styled-jsx and the mail preview inject style elements without a
 * nonce; injected CSS cannot run code), so no nonce in `style-src`: one would
 * switch `'unsafe-inline'` off. Local development adds `'unsafe-eval'` (React's
 * debugging) and `ws:` (hot reload); a production build never does.
 *
 * `CSC_CSP_REPORT_ONLY=1` sends the same policy as
 * `Content-Security-Policy-Report-Only` (emergency switch, 8.164).
 */

export const CSP_HEADER = 'Content-Security-Policy'
export const CSP_REPORT_ONLY_HEADER = 'Content-Security-Policy-Report-Only'

/** The tile server of the Location Map (FOSSGIS e.V., decision 8.171): images only. */
export const MAP_TILE_ORIGIN = 'https://tile.openstreetmap.de'

export type CspOptions = {
  nonce: string
  /** local development (`next dev`) */
  dev?: boolean
  /** NEXT_PUBLIC_STATIC_BASE_URL: images only come from there besides the app */
  staticBaseUrl?: string
}

/** 128 random bits, base64. */
export function newNonce(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

/** The origin of the static host, or null when unset or not an http(s) URL. */
export function staticOrigin(value: string | undefined): string | null {
  const text = (value ?? '').trim()
  if (!text) return null
  try {
    const url = new URL(text)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.origin : null
  } catch {
    return null
  }
}

export function buildCsp({ nonce, dev = false, staticBaseUrl }: CspOptions): string {
  const staticHost = staticOrigin(staticBaseUrl)
  const directives: Array<[string, string[]]> = [
    ['default-src', ["'self'"]],
    ['script-src', ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'", "'wasm-unsafe-eval'",
      ...(dev ? ["'unsafe-eval'"] : [])]],
    ['style-src', ["'self'", "'unsafe-inline'"]],
    ['img-src', ["'self'", 'blob:', 'data:', MAP_TILE_ORIGIN, ...(staticHost ? [staticHost] : [])]],
    ['connect-src', ["'self'", ...(dev ? ['ws:'] : [])]],
    ['font-src', ["'self'"]],
    ['worker-src', ["'self'", 'blob:']],
    ['media-src', ["'self'", 'blob:']],
    ['frame-src', ['https://maps.google.com', 'https://www.google.com']],
    ['object-src', ["'none'"]],
    ['base-uri', ["'none'"]],
    ['form-action', ["'self'"]],
    ['frame-ancestors', ["'none'"]],
  ]
  return directives.map(([name, sources]) => `${name} ${sources.join(' ')}`).join('; ')
}

/** Only the text `1` switches the report-only mode on. */
export function isReportOnly(value: string | undefined): boolean {
  return (value ?? '').trim() === '1'
}

export function cspHeaderName(reportOnly: boolean): string {
  return reportOnly ? CSP_REPORT_ONLY_HEADER : CSP_HEADER
}
