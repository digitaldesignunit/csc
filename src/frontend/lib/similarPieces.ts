/**
 * The pure parts of the "Similar pieces" card of the component page (decision
 * 8.174): the request to `GET /identities/{id}/similar`, what its answers and
 * refusals mean for the card, and the words under a neighbour. The card is
 * shown only when there is something to show: a piece without the descriptor
 * (422), a catalog whose matrix has not been built (409), a piece that is not
 * there for this viewer (404) and a piece without neighbours leave no card.
 */
import { rowName, rowNumber } from '@/lib/browse'
import { BackendError } from '@/lib/backend'
import { SHAPE_CLASS_LABELS, vocabLabel } from '@/generated/Vocab'
import type { SimilarPiece, SimilarPieces } from '@/generated/CatalogModels'

/** The card shows the six nearest. It asks for one more than that, so a seventh
 *  neighbour in the answer is what tells it that "Show more" has something to show;
 *  "Show more" then asks for the larger number. */
export const SIMILAR_CARD_COUNT = 6
export const SIMILAR_FIRST_COUNT = SIMILAR_CARD_COUNT + 1
export const SIMILAR_MORE_COUNT = 24

/** The basis of the card: the full radial signature, the shape as a whole. */
export const SIMILAR_BASIS = 'radial_signature'

export function similarPath(identityId: string, count: number = SIMILAR_FIRST_COUNT): string {
  const query = new URLSearchParams({ basis: SIMILAR_BASIS, count: String(count) })
  return `/identities/${encodeURIComponent(identityId)}/similar?${query.toString()}`
}

/** What the card does with an answer: hidden, or the neighbours to list. */
export type SimilarCard =
  | { kind: 'hidden'; reason: 'none' | 'no_descriptor' | 'no_matrix' | 'not_found' | 'error' }
  | { kind: 'list'; pieces: SimilarPiece[] }

export function cardOfAnswer(answer: SimilarPieces | null | undefined): SimilarCard {
  const pieces = answer?.results ?? []
  return pieces.length ? { kind: 'list', pieces } : { kind: 'hidden', reason: 'none' }
}

/** A refusal or a failure of the request; none of them is worth an error box
 *  on a page that is about something else. */
export function cardOfError(error: unknown): SimilarCard {
  const status = error instanceof BackendError ? error.status : 0
  if (status === 422) return { kind: 'hidden', reason: 'no_descriptor' }
  if (status === 409) return { kind: 'hidden', reason: 'no_matrix' }
  if (status === 404) return { kind: 'hidden', reason: 'not_found' }
  return { kind: 'hidden', reason: 'error' }
}

/** Whether "Show more" is offered: the answer holds more neighbours than the card shows,
 *  so exactly six (the card full, nothing behind it) offers nothing. */
export function canShowMore(found: number, shown: number = SIMILAR_CARD_COUNT): boolean {
  return found > shown
}

/** The neighbours the card lists: all that were loaded when expanded, else the nearest six.
 *  The ranking does not depend on how many are asked, so the six are the first six. */
export function shownPieces<T>(loaded: T[], expanded: boolean): T[] {
  return expanded ? loaded : loaded.slice(0, SIMILAR_CARD_COUNT)
}

/** "Show more" while collapsed and more than six were found; "Show fewer" while expanded; else nothing. */
export function toggleLabel(loaded: number, expanded: boolean): 'Show more' | 'Show fewer' | null {
  if (expanded) return 'Show fewer'
  return canShowMore(loaded) ? 'Show more' : null
}

/** After "Show fewer" the card is scrolled back to its top when that has left the
 *  viewport (the top edge is above it). */
export function needsScrollBack(cardTop: number): boolean {
  return cardTop < 0
}

/** "#584 / irregular": the line under the name of a neighbour. */
export function neighbourLine(piece: SimilarPiece['piece']): string {
  const shape = piece.shape_class ? vocabLabel(SHAPE_CLASS_LABELS, piece.shape_class).toLowerCase() : ''
  return [rowNumber(piece), shape].filter(Boolean).join(' / ')
}

/** The distance as the card prints it (standardised units, two decimals). */
export function distanceText(distance: number): string {
  return Number.isFinite(distance) ? distance.toFixed(2) : ''
}

/** The tooltip of a neighbour: its name and how far it is. */
export function neighbourTitle(item: SimilarPiece): string {
  return `${rowName(item.piece)}, distance ${distanceText(item.distance)} (smaller is more similar)`
}
