/**
 * Whether an element was ever published: the test the web uses wherever the
 * backend asks `identity_ever_published` (`apps/catalog/api/access.py`,
 * `EVER_PUBLISHED = ('published', 'withdrawn')`, spec 3.1.5), decision 8.193.
 *
 * `current_snapshot_id` is not that test: it is empty once every version is
 * withdrawn, although the element was published and the rules that follow
 * publication still hold. It keeps its other meaning, the version shown by
 * default, everywhere else.
 *
 * The rows come from `GET /identities/{id}/snapshots`, which keeps a withdrawn
 * version as a bare row for a caller outside the dataset (`tombstones=True`),
 * so the answer is the backend's for every caller who may see the element. A
 * caller without the rows passes none and gets the answer of
 * `current_snapshot_id` alone.
 */
export type VersionStatusRow = { status?: string | null }

const EVER_PUBLISHED = ['published', 'withdrawn']

export function everPublished(input: {
  currentSnapshotId?: string | null
  versions?: readonly VersionStatusRow[] | null
}): boolean {
  if (input.currentSnapshotId) return true
  return (input.versions ?? []).some((row) => EVER_PUBLISHED.includes(row.status ?? ''))
}
