// app/api/fetch-component-texture/route.ts
export const runtime = 'nodejs'

import { NextRequest, NextResponse } from 'next/server'
import { getToken } from 'next-auth/jwt'

const FASTAPI_URL = process.env.FASTAPI_URL!
const NEXTAUTH_SECRET = process.env.NEXTAUTH_SECRET || process.env.API_SECRET

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

  const res = await fetch(target, {
    method: 'GET',
    headers: { Authorization: `Bearer ${apiToken}` },
    cache: 'no-store',
    redirect: 'manual'
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    return new NextResponse(text, { status: res.status })
  }

  const contentType = res.headers.get('content-type') ?? 'image/jpeg'
  return new NextResponse(res.body, {
    status: 200,
    headers: { 'content-type': contentType }
  })
}
