/**
 * The document a record cites (decision 8.106): the title and, when the
 * record names an online source, the link --- shown as its host, opened in a
 * new tab. Only http and https links become links; anything else (a stored
 * value the backend would not take today) shows as text.
 */

export type DocumentRef = {
  title: string | null
  /** The link to open, or null when there is none or it is not http(s). */
  href: string | null
  /** The host to show: `example.org`, never the full path. */
  host: string | null
  /** The day the link was read, as stored (`YYYY-MM-DD`, `YYYY-MM` or `YYYY`). */
  retrievedAt: string | null
}

export function safeHref(value: unknown): { href: string; host: string } | null {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    if ((url.protocol !== 'http:' && url.protocol !== 'https:') || !url.hostname) return null
    return { href: url.toString(), host: url.hostname.replace(/^www\./, '') }
  } catch {
    return null
  }
}

/** The cited document of a payload (`payload.document`), or null when it has none. */
export function documentOf(payload: unknown): DocumentRef | null {
  const document = (payload as { document?: Record<string, unknown> } | null | undefined)?.document
  if (!document || typeof document !== 'object') return null
  const link = safeHref(document.url)
  return {
    title: typeof document.title === 'string' && document.title.trim() ? document.title.trim() : null,
    href: link?.href ?? null,
    host: link?.host ?? null,
    retrievedAt: typeof document.retrieved_at === 'string' && document.retrieved_at ? document.retrieved_at : null,
  }
}
