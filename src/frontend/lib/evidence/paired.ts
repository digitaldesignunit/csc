/**
 * The rebound record a core record is paired with (EN 13791 pairs, 0.6.3.1):
 * the card of the core links to it. The id is read from the payload of a
 * `core_compression` record; any other record, or a value that is no text,
 * has none.
 *
 * Run: npm test
 */

/** The `paired_rebound_id` of a core record's payload, or null. */
export function pairedReboundId(method: string, payload: unknown): string | null {
  if (method !== 'core_compression') return null
  const sampling = (payload as { sampling?: { paired_rebound_id?: unknown } } | null | undefined)?.sampling
  const id = sampling?.paired_rebound_id
  return typeof id === 'string' && id.trim() ? id.trim() : null
}

/** The anchor of a record's card on the component page (`EvidenceCard` ids). */
export function recordAnchor(recordId: string): string {
  return `#record-${recordId}`
}

/** The record is on this page: the link can point at its card. */
export function isOnPage(recordId: string, shownIds: readonly string[]): boolean {
  return shownIds.includes(recordId)
}

export const PAIRED_OFF_PAGE_TITLE =
  'This record is on another version or filtered out of this list'

export type PairedReboundLink =
  | { id: string; onPage: true; href: string }
  | { id: string; onPage: false; title: string }

/**
 * What the core's card shows for its paired rebound record: a link to the card
 * when that record is on the page (`shownIds`: the cards the page lists), else
 * the id as plain text with a short title saying why there is no link. Null for
 * a record that has no pairing. Without `shownIds` (a list that is no
 * component page: a queue, the form's review) nothing is on the page.
 */
export function pairedReboundLink(
  method: string,
  payload: unknown,
  shownIds?: readonly string[],
): PairedReboundLink | null {
  const id = pairedReboundId(method, payload)
  if (!id) return null
  if (shownIds && isOnPage(id, shownIds)) return { id, onPage: true, href: recordAnchor(id) }
  return { id, onPage: false, title: PAIRED_OFF_PAGE_TITLE }
}
