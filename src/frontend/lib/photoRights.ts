/**
 * Who may add and who may remove the photos of an existing version (the
 * controls of the "Photos and location" card; decision 8.184, issue #45).
 *
 * Mirrors the backend rule, which decides in the end: `_add_photo` and
 * `_remove_photo` in `apps/catalog/permissions.py` (actions `add_photo` and
 * `delete_photo`, called by `PUT` and `DELETE /snapshots/{id}/photos/{index}`):
 *
 * - before publish (status not `published` or `withdrawn`) both are
 *   `_file_editor`, that is `_unpublished_editor` for a version: a draft ---
 *   its author or a moderator of the dataset; a pending one --- a moderator
 *   only; a rejected one --- nobody;
 * - after publish (`published`) adding is for a contributor or moderator of the
 *   dataset, removing for a moderator only; a `withdrawn` version counts as
 *   published for removing;
 * - a site admin passes every check, and an anonymous caller none;
 * - except that nobody adds a photo to a withdrawn version, or to any version of
 *   a withdrawn element, a site admin included: the state refuses with a 409
 *   (`put_snapshot_photo`, decision 8.190). Removing is not part of that. A
 *   moderator reinstates first.
 */
export type PhotoRightsInput = {
  signedIn: boolean
  /** the id of the signed-in user (`Me._id`) */
  userId?: string | null
  isAdmin: boolean
  /** the viewer's roles in the dataset of the version */
  roles: readonly string[]
  /** the status of the version */
  status?: string | null
  /** `added_by_user_id` of the version */
  addedByUserId?: string | null
  /** the element is withdrawn (`identity.withdrawn` is set), whatever the version's status */
  identityWithdrawn?: boolean
}

export type PhotoRights = { add: boolean; remove: boolean }

export function photoRights(input: PhotoRightsInput): PhotoRights {
  if (!input.signedIn) return { add: false, remove: false }
  // the state refuses adding, for everyone (8.190); removing follows the role
  const open = !(input.status === 'withdrawn' || input.identityWithdrawn)
  if (input.isAdmin) return { add: open, remove: true }
  const moderator = input.roles.includes('moderator')
  const contributor = input.roles.includes('contributor')
  if (input.status === 'published' || input.status === 'withdrawn') {
    return { add: open && (contributor || moderator), remove: moderator }
  }
  const author = !!input.userId && input.userId === input.addedByUserId
  const editor =
    input.status === 'draft' ? moderator || author : input.status === 'pending' && moderator
  return { add: open && editor, remove: editor }
}
