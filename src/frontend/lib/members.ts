/**
 * The member editor of a dataset (decision 8.144 d): the e-mail address of a
 * member is shown to admins and to moderators of a reviewed dataset only, so
 * a member row may come without one.
 */

type MemberLike = { user_id: string; username?: string | null; email?: string | null }

/** The line under a member's name: the user name and, when it came, the address. */
export function memberLine(member: MemberLike): string {
  if (!member.username) return member.user_id
  return member.email ? `${member.username} \u00b7 ${member.email}` : member.username
}

/** What to call a member in a question: the user name, else the address, else a word. */
export function memberLabel(member: MemberLike): string {
  return member.username || member.email || 'this person'
}

type RoleMember = { user_id: string; roles: readonly string[] }

/**
 * Why a member's moderator role cannot be taken away or the member removed, or
 * null: a dataset keeps at least one moderator unless an admin acts (decision
 * 8.139 g; `put_dataset_member` answers 409). Only the last moderator is locked.
 */
export function lastModeratorReason(
  members: readonly RoleMember[],
  member: RoleMember,
  isAdmin: boolean,
): string | null {
  if (isAdmin || !member.roles.includes('moderator')) return null
  const moderators = members.filter((m) => m.roles.includes('moderator'))
  if (moderators.length !== 1 || moderators[0].user_id !== member.user_id) return null
  return 'A dataset keeps at least one moderator: add another before you remove or demote the last one (an admin can).'
}

/**
 * Why deleting a dataset will be refused before the user asks (decision 8.139 f):
 * the list counts the published elements the caller sees, so a count above zero
 * is certain and a count of zero is not (a draft or withdrawn element also holds
 * the dataset back).
 */
export function deleteDatasetReason(componentCount: number | null | undefined): string | null {
  if (typeof componentCount !== 'number' || componentCount <= 0) return null
  return `It still holds ${componentCount} published component${componentCount === 1 ? '' : 's'}: move ${componentCount === 1 ? 'it' : 'them'} to another dataset first (Actions menu of the component, Move).`
}

/** The hint under "Add a person": a moderator of an unreviewed dataset invites, whoever the address is. */
export function addMemberHint(reviewed: boolean | undefined, isAdmin: boolean): string {
  if (isAdmin || reviewed !== false) {
    return 'An existing account is added right away; any other address gets an invitation.'
  }
  return 'The person gets an invitation by mail. An existing account accepts it by signing in with that address; '
    + 'anyone else creates an account from the link. An admin adds people directly once the dataset is reviewed.'
}
