// app/api/fetch-component-texture/route.ts
export const runtime = 'nodejs'

import { NextRequest, NextResponse } from 'next/server'
import { getToken } from 'next-auth/jwt'

const FASTAPI_URL = process.env.FASTAPI_URL!
const NEXTAUTH_SECRET = process.env.NEXTAUTH_SECRET!

export async function GET(request: NextRequest) {
  const url = new URL(request.url)
  const component_id = url.searchParams.get('component_id')
  if (!component_id) {
    return NextResponse.json({ error: 'Missing component_id' }, { status: 400 })
  }

  // get FastAPI token from the user’s NextAuth JWT
  const jwt = await getToken({ req: request, secret: NEXTAUTH_SECRET })
  const apiToken = (jwt)?.apiToken
  if (!apiToken) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  // talk to FastAPI directly (bypass /api/backend hop)
  const target = `${FASTAPI_URL.replace(/\/+$/, '')}/components/${encodeURIComponent(component_id)}/texture`

  // Prepare headers including conditional request support
  const headers: Record<string, string> = { Authorization: `Bearer ${apiToken}` }
  const ifNoneMatch = request.headers.get('if-none-match')
  if (ifNoneMatch) {
    headers['if-none-match'] = ifNoneMatch
  }

  const res = await fetch(target, {
    method: 'GET',
    headers,
    cache: 'no-store',
    redirect: 'manual'
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    return new NextResponse(text, { status: res.status })
  }

  const contentType = res.headers.get('content-type') ?? 'image/jpeg'
  const responseHeaders: Record<string, string> = { 'content-type': contentType }
  
  // Pass through cache-related headers
  const etag = res.headers.get('etag')
  const cacheControl = res.headers.get('cache-control')
  if (etag) responseHeaders['etag'] = etag
  if (cacheControl) responseHeaders['cache-control'] = cacheControl

  return new NextResponse(res.body, {
    status: res.status,
    headers: responseHeaders
  })
}
