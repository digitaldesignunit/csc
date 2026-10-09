/**
 * The photo credit of one version (decision 8.128 a): who all its photos
 * come from. The pure parts: what to show and what the edit form sends.
 */

export type PhotoCredit = { text: string; url?: string | null }

/** The credit to show: trimmed, with a usable web address, or null. */
export function creditToShow(raw: unknown): { text: string; url: string | null } | null {
  if (!raw || typeof raw !== 'object') return null
  const { text, url } = raw as { text?: unknown; url?: unknown }
  const shown = typeof text === 'string' ? text.trim() : ''
  if (!shown) return null
  const address = typeof url === 'string' ? url.trim() : ''
  return { text: shown, url: /^https?:\/\//i.test(address) ? address : null }
}

/**
 * The text as the web shows it: "(c)" is written as the copyright sign (the
 * stored text stays ASCII).
 */
export function creditDisplayText(text: string): string {
  return text.replace(/\(c\)/gi, '\u00a9')
}

/** The two inputs of "Edit details" as the PATCH value: no text means no credit. */
export function creditFromInputs(text: string, url: string): { text: string; url: string | null } | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  return { text: trimmed, url: url.trim() || null }
}

/** The inputs' problem as a sentence, or '' when they can be sent. */
export function creditInputProblem(text: string, url: string): string {
  if (!text.trim() && url.trim()) return 'Add the credit text, or clear the link.'
  if (text.trim().length > 300) return 'The credit text is at most 300 characters.'
  if (url.trim() && !/^https?:\/\//i.test(url.trim())) return 'The link must start with http:// or https://.'
  if (url.trim().length > 500) return 'The link is at most 500 characters.'
  return ''
}
