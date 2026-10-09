/**
 * Scanners accept a raw UUID or any URL whose last path segment is a UUID
 * (spec section 7.5), so a future URL-bearing tag works without a code
 * change: `.../id/<uuid>`, `.../components/<uuid>`, or the bare id.
 */
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i

export function uuidFromScan(text: string | null | undefined): string | null {
  const raw = (text ?? '').trim()
  if (!raw) return null
  const exact = raw.match(new RegExp(`^${UUID.source}$`, 'i'))
  if (exact) return exact[0].toLowerCase()
  let path = raw
  try {
    path = new URL(raw).pathname
  } catch {
    // not a URL: treat as a path
  }
  const last = path.split(/[/?#]/).filter(Boolean).pop() ?? ''
  const match = last.match(new RegExp(`^${UUID.source}$`, 'i'))
  return match ? match[0].toLowerCase() : null
}
