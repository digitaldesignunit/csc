import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { getToken } from 'next-auth/jwt'

export async function middleware(req: NextRequest) {
  // Use the SAME secret as in NextAuth config
  const secret = process.env.API_SECRET
  const token = await getToken({ req, secret })
  if (!token) {
    const url = new URL('/auth/signin', req.url)
    url.searchParams.set('callbackUrl', req.nextUrl.pathname + req.nextUrl.search)
    return NextResponse.redirect(url)
  }
  return NextResponse.next()
}

export const config = {
  matcher: [
    '/components/:path*',   // protect your pages
    '/dashboard/:path*',    // protect the dashboard too
    '/admin/:path*',        // protect admin routes
    '/api/backend/:path*',  // protect the catch-all proxy too
  ],
}
