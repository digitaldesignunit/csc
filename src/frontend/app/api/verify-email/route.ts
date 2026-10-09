import { NextResponse } from 'next/server'
import { CSC_CLIENT_HEADERS } from '@/lib/cscClient'
import { forwardedFor } from '@/lib/clientAddress'

const FASTAPI_URL = process.env.FASTAPI_URL!

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url)
  const token = searchParams.get('token')

  try {
    const upstream = await fetch(
      `${FASTAPI_URL}/auth/verify-email?token=${encodeURIComponent(token || '')}`,
      { method: 'GET', headers: { ...CSC_CLIENT_HEADERS, ...forwardedFor(req.headers) } }
    )

    const contentType = upstream.headers.get('content-type')
    
    if (contentType?.includes('application/json')) {
      const data = await upstream.json()
      return NextResponse.json(data, { status: upstream.status })
    } else {
      const text = await upstream.text()
      console.error('Non-JSON response from FastAPI:', text.substring(0, 200))
      return NextResponse.json(
        { detail: 'Invalid response from server' },
        { status: 500 }
      )
    }
  } catch (error) {
    console.error('Error verifying email:', error)
    return NextResponse.json(
      { detail: 'Failed to verify email' },
      { status: 500 }
    )
  }
}

