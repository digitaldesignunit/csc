/**
 * The counts line of a dataset card (plan P11 stage 3, decision 8.118 2.13):
 * "3 members, 120 components". The member count is there for moderators and
 * admins only; a missing number is left out, not shown as zero.
 */
type CountsLike = { member_count?: number | null; component_count?: number | null }

export function datasetCounts(dataset: CountsLike): string {
  const plural = (n: number, one: string, many: string) => `${n.toLocaleString('en-US')} ${n === 1 ? one : many}`
  const parts: string[] = []
  if (typeof dataset.member_count === 'number') parts.push(plural(dataset.member_count, 'member', 'members'))
  if (typeof dataset.component_count === 'number') parts.push(plural(dataset.component_count, 'component', 'components'))
  return parts.join(', ')
}

/**
 * The id a dataset gets from its name (decision 8.139 d, `slug_from_name` of
 * the API): ASCII lower-case letters, digits and underscores, 2 to 55
 * characters. A number is added by the server when the id is taken; the id
 * never changes afterwards.
 */
export function slugFromName(name: string): string {
  const folded = name.normalize('NFKD').replace(/[^\x00-\x7f]/g, '').toLowerCase()
  const slug = folded.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 55).replace(/^_+|_+$/g, '')
  const base = slug || 'dataset'
  return base.length >= 2 ? base : `${base}_x`
}

type ReviewLike = { reviewed?: boolean | null }

/** A dataset waits for an administrator's review (8.139 c); an older one without the flag counts as reviewed. */
export function awaitsReview(dataset: ReviewLike): boolean {
  return dataset.reviewed === false
}

/** Why a dataset that awaits review cannot be catalog-visible or have public pieces. */
export const REVIEW_EXPLANATION =
  'An administrator reviews a new dataset first. Until then it stays members only and its pieces cannot be made public.'

/** The line under the name field of "New dataset". */
export function newDatasetHint(name: string): string {
  return name.trim()
    ? `Id: ${slugFromName(name)} (a number is added if it is taken; it cannot be changed later)`
    : 'The id is made from the name and cannot be changed later; the name can.'
}
