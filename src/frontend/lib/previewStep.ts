/**
 * Stepping through the items of the preview (decision 8.141 a): the index
 * `delta` places from `position`, or null at either end of the list or when
 * the shown item is not among them.
 */
export function stepIndex(position: number, length: number, delta: 1 | -1): number | null {
  if (position < 0 || position >= length) return null
  const next = position + delta
  return next >= 0 && next < length ? next : null
}
