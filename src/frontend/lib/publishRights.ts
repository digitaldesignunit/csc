/**
 * Who may publish the first version of a cut or merged element (decision 8.8,
 * issue #46): `_publish` in `apps/catalog/permissions.py` wants `moderator(D)`
 * and, for the first version of a child, a moderator of the dataset of every
 * parent as well. The route collects the parents in `_publish` of
 * `snapshot_lifecycle.py`: only for a first version (no version of the element
 * is `published` or `withdrawn`), and a parent that is no longer there is
 * skipped.
 *
 * The web reads each parent with `GET /identities/{id}?expand=none`:
 * - 200 with a `dataset`: the caller must moderate it;
 * - 401, 403 or a tombstone (a withdrawn parent seen from outside its
 *   dataset): the caller is no member of it, so not a moderator;
 * - 404 or 410: the backend skips the parent, no constraint.
 * A site admin passes every check.
 */
export type ParentLookup =
  | { kind: 'dataset'; dataset: string }
  | { kind: 'refused' }
  | { kind: 'gone' }

/** No version of the element is `published` or `withdrawn` (the backend's `first`). */
export function isFirstPublish(rows: readonly { status?: string | null }[]): boolean {
  return !rows.some((row) => row.status === 'published' || row.status === 'withdrawn')
}

/** What the queue says on a card whose element is withdrawn (8.190: the route answers 409). */
export const IDENTITY_WITHDRAWN_PUBLISH =
  'This component is withdrawn: reinstate it before publishing this snapshot.'

/**
 * Why a pending version of the queue has no Publish: the element is withdrawn (8.190), else what
 * the parents say (`parentsRefusePublish`, or 'loading' until they answered). Null: it can be
 * published. Reject and Delete stay either way.
 */
export function publishBlockOf(input: { identityWithdrawn?: boolean | null; parentBlock: string | null }): string | null {
  if (input.identityWithdrawn) return IDENTITY_WITHDRAWN_PUBLISH
  return input.parentBlock
}

/** Why the caller may not publish, or null when the parents do not stop them. */
export function parentsRefusePublish(input: {
  first: boolean
  moderates: (dataset: string) => boolean
  parents: readonly ParentLookup[]
}): string | null {
  if (!input.first) return null
  const blocking = input.parents.filter((parent) => (
    parent.kind === 'refused' || (parent.kind === 'dataset' && !input.moderates(parent.dataset))
  ))
  if (blocking.length === 0) return null
  const names = Array.from(new Set(blocking.flatMap((parent) => (parent.kind === 'dataset' ? [parent.dataset] : []))))
  const where = names.length > 0 ? ` (${names.join(', ')})` : ''
  return 'The first snapshot of a cut or merged component is published by a moderator of the dataset of every '
    + `parent as well${where}.`
}
