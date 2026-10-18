/**
 * The backend's read-only flag as the web app sees it (decision 8.154). While
 * the maintenance file exists on the server, the backend answers every write
 * with 503 and reports `read_only: true` on `/version`. The app asks `/version`
 * once on load and then once a minute while the tab is visible (one poll in one
 * provider, never one per component), shows a banner, and disables its write
 * actions. Pure helpers here, so the unit test covers them.
 */

/** Poll interval of the one provider. */
export const READ_ONLY_POLL_MS = 60_000

export const READ_ONLY_BANNER =
  'The catalog is read-only while we do maintenance. You can browse, but changes cannot be saved right now.'

export const READ_ONLY_TITLE = 'Not available while the catalog is read-only (maintenance)'

/** The answer of the backend that a write got during maintenance. */
export const READ_ONLY_DETAIL = 'read-only: maintenance'

/** `true` only for `{ read_only: true }`; anything else (an older backend without the field, an error body) is off. */
export function parseReadOnly(body: unknown): boolean {
  return typeof body === 'object' && body !== null && (body as { read_only?: unknown }).read_only === true
}

/** The route of the version answer, through the web app's proxy (public reads need no sign-in). */
export const VERSION_PATH = '/api/backend/version'
