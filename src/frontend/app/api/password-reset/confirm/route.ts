import { NextResponse } from 'next/server'
import { CSC_CLIENT_HEADERS } from '@/lib/cscClient'
import { forwardedFor } from '@/lib/clientAddress'

const FASTAPI_URL = process.env.FASTAPI_URL!

/** Anonymous: the mailed token and the new password (decision 8.124). */
export async function POST(req: Request) {
  const body = await req.json().catch(() => ({}))
  const upstream = await fetch(`${FASTAPI_URL}/auth/password-reset/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...CSC_CLIENT_HEADERS, ...forwardedFor(req.headers) },
    body: JSON.stringify(body),
  })
  const data = await upstream.json().catch(() => ({}))
  return NextResponse.json(data, { status: upstream.status })
}
