/** Who may open an /admin page (decision 8.118 M6): the layout shows an access
 *  notice instead of a silent redirect. */
export type AdminNeed = 'admin' | 'moderator' | 'moderator-or-reviewer'

export function adminPageNeed(pathname: string): AdminNeed {
  if (/^\/admin\/(validation|review)(\/|$)/.test(pathname)) return 'moderator-or-reviewer'
  if (/^\/admin\/datasets(\/|$)/.test(pathname)) return 'moderator'
  return 'admin'
}

export const ADMIN_NOTICE: Record<AdminNeed, string> = {
  admin: 'This page is for administrators.',
  moderator: 'This page is for moderators of a dataset and for administrators.',
  'moderator-or-reviewer': 'This page is for moderators and reviewers of a dataset, and for administrators.',
}
