/**
 * The public switch (decision 8.131): who sees the control, and what the
 * confirmation tells anonymous visitors then get to see. Pure, so the unit
 * test covers it.
 */

/**
 * Whoever may PATCH the identity's metadata (8.9): `moderator(D)`, or the
 * creator while nothing of the piece was published.
 */
export function canSwitchPublic(input: {
  moderates: boolean
  isCreator: boolean
  everPublished: boolean
}): boolean {
  return input.moderates || (input.isCreator && !input.everPublished)
}

/** What a visitor without an account sees of a public piece (8.101, 8.13, 7.13). */
export const PUBLIC_EXPOSES: readonly string[] = [
  'the piece with its data and its photos (location data is removed from the photos)',
  'its evidence records with the organisations only, no people',
  'the attachments of the evidence, listed with "sign in to download"',
]

export function publicConfirmText(subject: string): string {
  return `${subject} Anyone without an account then sees: ${PUBLIC_EXPOSES.join('; ')}.`
}

/** The label of a dataset action with the number it affects, or "..." until it is known. */
export function datasetPublicLabel(makePublic: boolean, count: number | null): string {
  const base = makePublic ? 'Make all published pieces public' : 'Make all published pieces private'
  return count === null ? base : `${base} (${count})`
}

/** One sentence under the dataset action: what it changes and what it leaves. */
export function datasetPublicHelp(count: number | null, makePublic: boolean): string {
  if (count === null) return 'Counting...'
  if (count === 0) return makePublic ? 'No published piece is private.' : 'No published piece is public.'
  const pieces = count === 1 ? '1 published piece' : `${count} published pieces`
  return `${pieces} would become ${makePublic ? 'public' : 'private'}. Unpublished and withdrawn pieces and other datasets stay as they are.`
}
