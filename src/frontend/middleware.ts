import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { getToken } from 'next-auth/jwt'

export async function middleware(req: NextRequest) {
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

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/components/:path*',   // protect your pages
    '/components',          // protect components root
    '/dashboard/:path*',    // protect the dashboard too
    '/dashboard',           // protect dashboard root
    '/admin/:path*',        // protect admin routes
    '/api/backend/:path*',  // protect the catch-all proxy too
    '/gh-interface/:path*', // protect the gh-interface too
    '/gh-interface',        // protect gh-interface root
    '/designs/:path*',      // protect designs subpages
    '/designs',             // protect designs root - THIS WAS MISSING!
    '/findcomponent/:path*', // protect find component subpages
    '/findcomponent',       // protect find component root
    '/identify/:path*',     // protect identify subpages
    '/identify',            // protect identify root
    '/analytics/:path*',    // protect analytics subpages
    '/analytics',           // protect analytics root
  ],
}
