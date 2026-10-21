/**
 * The consent page of a connector (decision 8.168 b), `/oauth/consent`: what it
 * shows and where it may send the browser. Pure, so the unit test covers it.
 */
export type ConsentView = {
  redirect_host: string
  redirect_is_loopback: boolean
  client_name?: string | null
  /** read:catalog (a tool such as Claude) or gh:client (Grasshopper on this computer) */
  scope?: string
  /** the computer name Grasshopper sent: shown as text nobody checked */
  computer?: string | null
  access: string
  can_allow: boolean
  refusal?: string | null
}

export type ConsentResult = { redirect_to: string }

/** The request id of the link: what `/authorize` made, url-safe base64 of 32 bytes. */
export function requestId(value: string | null | undefined): string | null {
  const id = (value ?? '').trim()
  return /^[A-Za-z0-9_-]{20,128}$/.test(id) ? id : null
}

/**
 * Where the answer may send the browser: the callback of Claude, or a
 * loopback callback of a tool on this computer. The backend builds the
 * address from the redirect URI it validated; this checks it once more, so
 * that nothing else is ever opened from this page.
 */
export function safeReturnUrl(value: string): string | null {
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return null
  }
  if (url.username || url.password || url.hash) return null
  if (url.protocol === 'https:' && url.host === 'claude.ai' && url.pathname === '/api/mcp/auth_callback') {
    return url.toString()
  }
  if (
    url.protocol === 'http:' &&
    (url.hostname === 'localhost' || url.hostname === '127.0.0.1') &&
    url.pathname === '/callback'
  ) {
    return url.toString()
  }
  return null
}

export const ACCESS_LINE = 'Read access to the catalog, as you see it'

export const LOOPBACK_WARNING =
  'This address is on your own computer. Allow only if you started this connection yourself, from a tool you run.'

export const GONE_TEXT =
  'This connection request is no longer valid. Start the connection again in the tool.'

export const GH_SCOPE = 'gh:client'

export const GH_LOOPBACK_WARNING =
  'This address is on your own computer. Allow only if you pressed SignIn in Grasshopper on this computer just now.'

export function isGrasshopper(view: Pick<ConsentView, 'scope'>): boolean {
  return view.scope === GH_SCOPE
}

/** The title of the card. */
export function consentTitle(view: Pick<ConsentView, 'scope'>): string {
  return isGrasshopper(view) ? 'Sign in Grasshopper on this computer' : 'Connect a tool to the catalog'
}

/** The sentence under the host: what Allow does. */
export function allowText(host: string, view: Pick<ConsentView, 'scope'> = {}): string {
  if (isGrasshopper(view)) {
    return `If you allow, you are sent back to ${host}, this computer, and Grasshopper here can act as you in the Grasshopper interface, until you sign out in Grasshopper or revoke it under Settings, Access tokens.`
  }
  return `If you allow, you are sent back to ${host} and that tool can read the catalog as you, until you revoke it under Settings, Access tokens.`
}
