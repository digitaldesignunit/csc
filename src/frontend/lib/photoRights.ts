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
 * - after publish (`published`, and `withdrawn`, which the backend counts as
 *   published) adding is for a contributor or moderator of the dataset,
 *   removing for a moderator only;
 * - a site admin passes every check, and an anonymous caller none.
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
}

export type PhotoRights = { add: boolean; remove: boolean }

export function photoRights(input: PhotoRightsInput): PhotoRights {
  if (!input.signedIn) return { add: false, remove: false }
  if (input.isAdmin) return { add: true, remove: true }
  const moderator = input.roles.includes('moderator')
  const contributor = input.roles.includes('contributor')
  if (input.status === 'published' || input.status === 'withdrawn') {
    return { add: contributor || moderator, remove: moderator }
  }
  const author = !!input.userId && input.userId === input.addedByUserId
  const editor =
    input.status === 'draft' ? moderator || author : input.status === 'pending' && moderator
  return { add: editor, remove: editor }
}
