/**
 * What the session monitor does when the session ends on a component page
 * (issue 35). A piece that is public to anonymous visitors stays readable, drawn
 * again as an anonymous visitor sees it; the rest of the page (a private piece,
 * a draft or pending version, a layout opened by `?layout=`, a record only the
 * signed-in user may see) is not shown to a signed-out visitor, so the user is
 * signed out and sent to the sign-in page, which returns to the same address.
 *
 * The component page tells the monitor what it shows (`PageView`); the path
 * alone does not say whether the piece is public.
 */
import { PUBLIC_COMPONENT_DETAIL_PATH } from '@/lib/publicAccess'

/** What the component page on screen reports. `null`: no component page reports. */
export type PageView = { publicToAnonymous: boolean } | null

export type PageViewInput = {
  /** `identity.is_public` of the piece */
  isPublic?: boolean | null
  /** status of the version on screen */
  snapshotStatus?: string | null
  /** `?layout=<evidence id>`: loaded by id, may be a record only the signed-in user may load */
  layoutId?: string | null
  /** the version rows the page lists (History card, Actions menu): the author and the
   *  moderators see drafts, pending and rejected ones there, the members a withdrawn one in full */
  snapshots?: ReadonlyArray<VersionRow> | null
  /** statuses of the evidence records on screen; `null` while they load */
  recordStatuses?: ReadonlyArray<string | null | undefined> | null
}

type VersionRow = {
  status?: string | null
  name?: string | null
  added_by_user_id?: string | null
  added_by_username?: string | null
}

/** A version row an anonymous visitor does not get: a draft, pending or rejected version, or a
 *  withdrawn one in full. The public tombstone of a withdrawn version is a bare row: no name, no
 *  author; any of them set makes it a full row. */
function versionRowIsPrivate(row: VersionRow): boolean {
  if (row.status === 'draft' || row.status === 'pending' || row.status === 'rejected') return true
  return row.status === 'withdrawn'
    && (row.name != null || row.added_by_user_id != null || row.added_by_username != null)
}

/** True when an anonymous visitor would see everything the page shows. */
export function componentViewIsPublic(input: PageViewInput): boolean {
  if (input.isPublic !== true) return false
  if (input.snapshotStatus !== 'published') return false
  if (input.layoutId) return false
  if (input.snapshots?.some(versionRowIsPrivate)) return false
  if (input.recordStatuses?.some((status) => status !== 'published')) return false
  return true
}

/**
 * What happens when the session ended (decision 8.182 a):
 * - `anonymous`: a public view of a component page. The user is signed out
 *   without leaving the page, which is drawn again as an anonymous visitor
 *   sees it: readable, without the data only a signed-in user gets (names of
 *   people, e-mails, the people of the History graph).
 * - `sign-in`: every other page, a private piece, a draft or layout view. The
 *   user is signed out and sent to sign-in; no private data stays on screen.
 * A path that is no component page, and a component page that reports nothing
 * (an access notice, a piece without a published version), is `sign-in`.
 */
export type ExpiryOutcome = 'anonymous' | 'sign-in'

export function expiryOutcome(pathname: string, view: PageView): ExpiryOutcome {
  return PUBLIC_COMPONENT_DETAIL_PATH.test(pathname) && view?.publicToAnonymous === true
    ? 'anonymous'
    : 'sign-in'
}

/** The sign-in address after the session ended: a component page is the callback, query and hash kept. */
export function expiredSignInUrl(pathname: string, search = '', hash = ''): string {
  const base = '/auth/signin?error=SessionExpired'
  if (!PUBLIC_COMPONENT_DETAIL_PATH.test(pathname)) return base
  return `${base}&callbackUrl=${encodeURIComponent(`${pathname}${search}${hash}`)}`
}
