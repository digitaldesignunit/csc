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

/** The hint under "Add a person": a moderator of an unreviewed dataset invites, whoever the address is. */
export function addMemberHint(reviewed: boolean | undefined, isAdmin: boolean): string {
  if (isAdmin || reviewed !== false) {
    return 'An existing account is added right away; any other address gets an invitation.'
  }
  return 'The person gets an invitation by mail. An existing account accepts it by signing in with that address; '
    + 'anyone else creates an account from the link. An admin adds people directly once the dataset is reviewed.'
}
