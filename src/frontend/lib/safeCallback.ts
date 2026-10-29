/**
 * The return address after sign-in (`?callbackUrl=`): only an address on this
 * site. A text that starts with one slash is a path of this site; `//host`,
 * `/\host` (browsers read the backslash as a slash), `https://host`,
 * `javascript:...` and control characters are not, and give the fallback.
 * The same check runs on the server (the sign-in page) and in the browser (the
 * form), so a link cannot send the user to another site after the password.
 */

/** Any origin does for the server, which only needs the path: the check is that the path stays on it. */
const SERVER_ORIGIN = 'http://csc.invalid'

export function safeCallbackPath(
  raw: string | string[] | null | undefined,
  fallback: string,
  origin: string = SERVER_ORIGIN,
): string {
  const value = Array.isArray(raw) ? raw[0] : raw
  if (typeof value !== 'string' || !value) return fallback
  // exactly one leading slash; no backslash and no control character anywhere
  if (!/^\/(?![/\\])/.test(value) || /[\u0000-\u001f\u007f\\]/.test(value)) return fallback
  try {
    const url = new URL(value, origin)
    if (url.origin !== new URL(origin).origin) return fallback
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return fallback
  }
}
