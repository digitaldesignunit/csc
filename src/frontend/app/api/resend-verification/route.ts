import { NextResponse } from 'next/server'

const FASTAPI_URL = process.env.FASTAPI_URL!

export async function POST(req: Request) {
  const body = await req.json()

  const upstream = await fetch(`${FASTAPI_URL}/auth/resend-verification`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const data = await upstream.json()

  return NextResponse.json(data, { status: upstream.status })
}

