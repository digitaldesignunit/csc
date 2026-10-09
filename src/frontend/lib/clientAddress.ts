/**
 * The address of the visitor, as the web server sees it, to pass on to the
 * backend (plan P10 review, decision 8.117 e).
 *
 * The browser reaches this server through the Uberspace web proxy, which
 * appends the address of the peer it talked to to `X-Forwarded-For`. The
 * backend only ever sees this server, so every visitor would share one rate
 * limit unless the address is passed on. What the browser put into the header
 * itself is on the left of the chain and never trusted: the address is the one
 * `CSC_PROXY_HOPS` proxies from the right (default 1: the Uberspace proxy;
 * 0 = no proxy in front, then nothing is known and nothing is sent).
 *
 * The backend gets it as a single-entry `X-Forwarded-For` and believes it only
 * when this server's own address is one of its trusted proxies
 * (`CSC_TRUSTED_PROXIES`, `limiter.py`).
 */

type HeaderBag =
  | Headers
  | Record<string, string | string[] | undefined | null>

const ADDRESS = /^(?:[0-9]{1,3}(?:\.[0-9]{1,3}){3}|[0-9a-fA-F:]*:[0-9a-fA-F:.]*)$/

function header(headers: HeaderBag, name: string): string {
  if (headers instanceof Headers) return headers.get(name) ?? ''
  for (const [key, value] of Object.entries(headers)) {
    if (key.toLowerCase() !== name) continue
    return Array.isArray(value) ? value.join(',') : (value ?? '')
  }
  return ''
}

export function proxyHops(env: string | undefined = process.env.CSC_PROXY_HOPS): number {
  const hops = Number.parseInt(env ?? '1', 10)
  return Number.isFinite(hops) && hops >= 0 ? hops : 1
}

/** The visitor's address, or null when there is none to trust. */
export function clientAddress(headers: HeaderBag, hops: number = proxyHops()): string | null {
  if (hops < 1) return null
  const chain = header(headers, 'x-forwarded-for')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
  if (chain.length < hops) return null
  const address = chain[chain.length - hops]
  return ADDRESS.test(address) ? address : null
}

/** The headers to add to a request to the backend. */
export function forwardedFor(headers: HeaderBag, hops: number = proxyHops()): Record<string, string> {
  const address = clientAddress(headers, hops)
  return address ? { 'X-Forwarded-For': address } : {}
}
