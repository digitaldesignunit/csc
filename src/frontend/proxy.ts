import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { getToken } from 'next-auth/jwt'
import { allowsAnonymousCatalogRead } from '@/lib/publicAccess'
import { isApiPath, isProtectedPath } from '@/lib/proxyAuth'
import { buildCsp, cspHeaderName, isReportOnly, newNonce } from '@/lib/csp'

/** Redirect to the sign-in page, or null when the visitor may pass. */
async function signInRedirect(req: NextRequest): Promise<NextResponse | null> {
  const { pathname } = req.nextUrl

  // Public component demos: detail page + read-only backend GETs (auth enforced by FastAPI).
  if (allowsAnonymousCatalogRead(pathname, req.method)) return null

  // Use the SAME secret as in NextAuth config
  const secret = process.env.NEXTAUTH_SECRET
  const token = await getToken({ req, secret })

  if (!token) {
    const url = new URL('/auth/signin', req.url)
    url.searchParams.set('callbackUrl', req.nextUrl.pathname + req.nextUrl.search)
    return NextResponse.redirect(url)
  }

  // Check if API token is expired
  if (token.error === 'ApiTokenExpired') {
    console.log('[Middleware] API token expired, redirecting to signin')
    const url = new URL('/auth/signin', req.url)
    url.searchParams.set('callbackUrl', req.nextUrl.pathname + req.nextUrl.search)
    url.searchParams.set('error', 'SessionExpired')
    return NextResponse.redirect(url)
  }

  // Additional check for API token expiry time
  if (token.apiTokenExpiresAt && Date.now() >= Number(token.apiTokenExpiresAt)) {
    console.log('[Middleware] API token expired (time check), redirecting to signin')
    const url = new URL('/auth/signin', req.url)
    url.searchParams.set('callbackUrl', req.nextUrl.pathname + req.nextUrl.search)
    url.searchParams.set('error', 'SessionExpired')
    return NextResponse.redirect(url)
  }

  return null
}

export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl

  if (isProtectedPath(pathname)) {
    const redirect = await signInRedirect(req)
    if (redirect) return redirect
  }

  // The API routes carry data, not documents: no policy, no nonce.
  if (isApiPath(pathname)) return NextResponse.next()

  // One Content-Security-Policy per request with a fresh nonce (decision
  // 8.164). Next reads the nonce from the policy on the request and puts it on
  // its own scripts; the layout reads `x-nonce` for next-themes.
  const nonce = newNonce()
  const policy = buildCsp({
    nonce,
    dev: process.env.NODE_ENV === 'development',
    staticBaseUrl: process.env.NEXT_PUBLIC_STATIC_BASE_URL || process.env.NEXT_STATIC_BASE_URL,
  })
  const header = cspHeaderName(isReportOnly(process.env.CSC_CSP_REPORT_ONLY))

  const requestHeaders = new Headers(req.headers)
  requestHeaders.set('x-nonce', nonce)
  requestHeaders.set(header, policy)

  const response = NextResponse.next({ request: { headers: requestHeaders } })
  response.headers.set(header, policy)
  return response
}

// Every path (the policy is per request), except the build output and the
// public folders that no sign-in gate covers. The sign-in gate inside `proxy`
// applies to the prefixes of lib/proxyAuth.ts, the gh-interface screenshots
// among them: no protected prefix may be excluded here (a test checks it).
export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon\\.ico|backgroundmeshes/|logo/).*)'],
}
