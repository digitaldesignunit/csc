/**
 * The datasets an element can be moved to (decision 8.191): `move_identity` in
 * `apps/catalog/permissions.py` wants a moderator of the source and of the
 * destination dataset, a site admin always; the destination is not the dataset
 * the element is in. The route refuses the rest (a draft or pending version or
 * record, a public element into a dataset an admin has not reviewed).
 */
export type MoveTarget = { id: string; name: string; reviewed: boolean }

type DatasetRow = { _id: string; name?: string | null; reviewed?: boolean | null }

export function moveTargets(input: {
  datasets: readonly DatasetRow[]
  /** the datasets the caller moderates (`Me.moderated_datasets`) */
  moderated: readonly string[]
  isAdmin: boolean
  /** the dataset the element is in */
  current: string | null | undefined
}): MoveTarget[] {
  const mine = new Set(input.moderated)
  return input.datasets
    .filter((row) => row._id !== input.current && (input.isAdmin || mine.has(row._id)))
    .map((row) => ({ id: row._id, name: row.name || row._id, reviewed: row.reviewed !== false }))
    .sort((a, b) => a.name.localeCompare(b.name))
}

/** Whether the route refuses this move for sure: a public element into an unreviewed dataset, by a non-admin (8.139 c). */
export function unreviewedRefuses(target: MoveTarget | undefined, isPublic: boolean | null | undefined, isAdmin: boolean): boolean {
  return !!target && !target.reviewed && !!isPublic && !isAdmin
}

/** The sentence for a destination an admin has not reviewed yet (8.139 c). */
export function unreviewedWarning(target: MoveTarget | undefined, isPublic: boolean | null | undefined, isAdmin: boolean): string | null {
  if (!target || target.reviewed || !isPublic) return null
  return isAdmin
    ? 'This dataset has not been reviewed yet; as an administrator you may move a public component into it.'
    : 'This component is public and this dataset has not been reviewed by an administrator yet: it cannot move there.'
}
