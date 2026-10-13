/**
 * Server-side calls to the backend from pages (decision 8.144, review F3).
 *
 * A page used to call its own `/api/backend` proxy through a base URL built
 * from the request's Host and X-Forwarded-Proto headers, which a request can
 * set. Now the page calls `FASTAPI_URL` itself: the login token comes from the
 * session cookie (`getToken`), the client header and the visitor's address are
 * added as the proxy adds them, and the browser's cookie never leaves this
 * server. Server-only: import it from pages and route handlers, never from a
 * client component.
 */
import { cookies, headers } from 'next/headers'
import { getToken } from 'next-auth/jwt'

import { forwardedFor } from '@/lib/clientAddress'
import { CSC_CLIENT_HEADERS } from '@/lib/cscClient'

type HeaderBag = Parameters<typeof forwardedFor>[0]

/** The URL and headers of one backend call. Pure; `serverBackend` adds the
 *  session. A path that does not start with one slash is refused, so a caller
 *  cannot be talked into another host. */
export function backendRequest(
  backendUrl: string,
  path: string,
  apiToken: string | undefined,
  requestHeaders: HeaderBag,
): { url: string; headers: Record<string, string> } {
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error('serverBackend: the path must start with one slash')
  }
  return {
    url: `${backendUrl.replace(/\/+$/, '')}${path}`,
    headers: {
      Accept: 'application/json',
      ...CSC_CLIENT_HEADERS,
      ...forwardedFor(requestHeaders),
      ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}),
    },
  }
}

async function apiTokenOfRequest(): Promise<string | undefined> {
  const token = await getToken({
    req: { cookies: await cookies(), headers: await headers() } as unknown as Parameters<typeof getToken>[0]['req'],
    secret: process.env.NEXTAUTH_SECRET,
  })
  const apiToken = token?.apiToken
  return typeof apiToken === 'string' && apiToken ? apiToken : undefined
}

/** True when the request carries a sign-in. */
export async function hasServerSession(): Promise<boolean> {
  return Boolean(await apiTokenOfRequest())
}

/** `GET`-style call of the backend as the signed-in visitor (or anonymous). */
export async function serverBackend(path: string): Promise<Response> {
  const { url, headers: out } = backendRequest(
    process.env.FASTAPI_URL!, path, await apiTokenOfRequest(), await headers())
  return fetch(url, { cache: 'no-store', headers: out })
}
