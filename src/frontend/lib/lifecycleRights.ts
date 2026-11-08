/**
 * Which lifecycle buttons of a version or an evidence record a caller sees
 * (decisions 8.18, 8.190, 8.193, 8.195). Each rule mirrors the backend, which
 * decides in the end:
 *
 * - `permissions.py` (`RULES`): `submit`, `recall`, `resubmit` are `_author`;
 *   a site admin passes every check except the two verification rules
 *   (`NO_ADMIN_SHORTCUT`), so an admin submits, recalls and returns to draft
 *   another person's record (6.5, #48 case 6);
 *   `publish`, `reject`, `withdraw`, `reinstate` are `moderator(D)`;
 *   `supersede_*` is `contributor(D)`; `delete_record` is the author or
 *   `moderator(D)` of a draft, pending or rejected record.
 * - a withdrawn element stays out of circulation (8.190): submit, publish,
 *   promote, correct and reinstate of a version answer 409 "The component is
 *   withdrawn." for everyone, an admin included (a version is reinstated after
 *   the element); so do submit, edit, publish and reinstate of an evidence
 *   record. Recall, reject, back to draft, delete and a plain withdraw stay;
 *   a withdraw with a replacement is refused, and the web never sends one.
 * - the state the route refuses with a 409: "Back to draft" of a rejected
 *   version while another version is open (`resubmit_snapshot`, I3b), a
 *   correction of a version while one is open (`supersede_snapshot`), a
 *   correction of an evidence record while a correction of it is open or the
 *   element is withdrawn (`supersede_evidence`, I14, I28). The web learns of
 *   the open ones through `has_open_snapshot` and `has_open_correction`
 *   (8.195), which the server computes for the members of the dataset and
 *   admins.
 */
export type CallerFacts = {
  /** the caller wrote the record (`added_by_user_id`, `recorded_by_user_id`) */
  isAuthor: boolean
  isAdmin: boolean
  /** `moderator(D)`; true for a site admin as well */
  isModerator: boolean
  /** `contributor(D)`; true for a site admin as well */
  isContributor: boolean
}

export type SnapshotButtons = {
  submit: boolean
  recall: boolean
  resubmit: boolean
  publish: boolean
  reject: boolean
  correct: boolean
  promote: boolean
  withdraw: boolean
  reinstate: boolean
  delete: boolean
}

export function snapshotButtons(input: CallerFacts & {
  status: string
  superseded: boolean
  isCurrent: boolean
  /** another version of the element is draft or pending (`has_open_snapshot`) */
  hasOpenSnapshot: boolean
  /** the element is withdrawn: no submit, publish, promote or correct (8.190) */
  identityWithdrawn?: boolean
  /** why a first publish is refused (`parentsRefusePublish`); null: nothing stops it */
  publishBlock?: string | null
}): SnapshotButtons {
  const { status } = input
  const owner = input.isAuthor || input.isAdmin
  const live = status === 'published' && !input.superseded
  const open = !input.identityWithdrawn
  return {
    submit: open && owner && status === 'draft',
    recall: owner && status === 'pending',
    resubmit: owner && status === 'rejected' && !input.hasOpenSnapshot,
    publish: open && input.isModerator && status === 'pending' && !input.publishBlock,
    reject: input.isModerator && status === 'pending',
    correct: open && input.isContributor && live && !input.hasOpenSnapshot,
    promote: open && input.isModerator && live && !input.isCurrent,
    withdraw: input.isModerator && status === 'published',
    // a version comes back after the element does (8.190)
    reinstate: open && input.isModerator && status === 'withdrawn',
    delete: (input.isAuthor || input.isModerator) && ['draft', 'pending', 'rejected'].includes(status),
  }
}

export type EvidenceButtons = {
  submit: boolean
  recall: boolean
  resubmit: boolean
  publish: boolean
  reject: boolean
  withdraw: boolean
  reinstate: boolean
  edit: boolean
  correct: boolean
  delete: boolean
}

export function evidenceButtons(input: CallerFacts & {
  status: string
  superseded: boolean
  /** a draft or pending correction of this record exists (`has_open_correction`) */
  hasOpenCorrection: boolean
  /** the element is withdrawn: no evidence is recorded or corrected on it (I28) */
  identityWithdrawn: boolean
}): EvidenceButtons {
  const { status } = input
  const owner = input.isAuthor || input.isAdmin
  const live = status === 'published' && !input.superseded
  // a withdrawn element takes no evidence step that moves a record forward: submit, edit and publish
  // answer 409 "The component is withdrawn (I28)"; reject, recall, back to draft and delete stay, so a
  // moderator can clear a record before a move
  const open = !input.identityWithdrawn
  return {
    // `submit` is the author's (`_author`): a moderator who did not write the draft is refused
    submit: open && owner && status === 'draft',
    recall: owner && status === 'pending',
    resubmit: owner && status === 'rejected',
    publish: open && input.isModerator && status === 'pending',
    reject: input.isModerator && status === 'pending',
    withdraw: input.isModerator && status === 'published',
    // `reinstate_evidence` answers 409 on a withdrawn element, like publish (8.190)
    reinstate: open && input.isModerator && status === 'withdrawn',
    // `canEditEvidence`: a draft is edited by its author or moderator(D), a pending record by moderator(D)
    edit: open && ((status === 'draft' && (input.isAuthor || input.isModerator))
      || (status === 'pending' && input.isModerator)),
    correct: input.isContributor && live && !input.hasOpenCorrection && !input.identityWithdrawn,
    delete: (input.isAuthor || input.isModerator) && ['draft', 'pending', 'rejected'].includes(status),
  }
}

/**
 * The files of an evidence record (`_add_photo`, `_remove_photo`, `_file_editor`
 * in `permissions.py`; routes `POST /evidence/attachments` and
 * `DELETE /evidence/{id}/attachments/{index}`):
 *
 * - before publish both are `_file_editor`: a draft is for its author or
 *   `moderator(D)`; a pending record for `moderator(D)` and the author of a
 *   pending correction (8.142 a); a rejected record has no editor, a site
 *   admin apart;
 * - after publish adding is for a contributor or a moderator of the dataset
 *   (#48 case 1), removing for a moderator;
 * - nobody adds to a withdrawn record or to any record of a withdrawn element,
 *   a site admin included: the state refuses with a 409 (8.190).
 */
export function attachmentButtons(input: CallerFacts & {
  status: string
  /** the record corrects another one (it has `supersedes`) */
  correction: boolean
  identityWithdrawn: boolean
}): { add: boolean; remove: boolean } {
  const { status } = input
  const published = status === 'published' || status === 'withdrawn'
  const ownCorrection = input.isAuthor && input.correction && status === 'pending'
  const editor = status === 'draft' ? input.isAuthor || input.isModerator
    : status === 'pending' ? input.isModerator || ownCorrection
      : false
  const open = status !== 'withdrawn' && !input.identityWithdrawn
  if (input.isAdmin) return { add: open, remove: true }
  if (published) return { add: open && (input.isContributor || input.isModerator), remove: input.isModerator }
  return { add: open && editor, remove: editor }
}
