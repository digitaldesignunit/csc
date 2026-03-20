// app/api/register/route.ts
import { NextResponse } from 'next/server'

const FASTAPI_URL = process.env.FASTAPI_URL!
const MAX_BODY_BYTES = 32 * 1024 // 32 KB

export async function POST(req: Request) {
  const contentLength = req.headers.get('content-length')
  if (contentLength && parseInt(contentLength) > MAX_BODY_BYTES) {
    return NextResponse.json({ error: 'Request too large' }, { status: 413 })
  }

  const body = await req.json()

  const upstream = await fetch(`${FASTAPI_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const data = await upstream.json()

  return NextResponse.json(data, { status: upstream.status })
}
