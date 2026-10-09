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
