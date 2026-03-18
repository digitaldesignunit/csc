// app/api/backend/[...path]/route.ts
export const runtime = 'nodejs'

import { NextRequest, NextResponse } from 'next/server'
import { getToken } from 'next-auth/jwt'

const FASTAPI_URL = process.env.FASTAPI_URL!
const NEXTAUTH_SECRET = process.env.NEXTAUTH_SECRET

function buildTargetUrl(pathParts: string[] | undefined, srcUrl: URL) {
  const path = Array.isArray(pathParts) && pathParts.length
    ? `/${pathParts.join('/')}`
    : ''
  const qs = srcUrl.search
  return `${FASTAPI_URL.replace(/\/+$/, '')}${path}${qs}`
}

function forwardableHeaders(req: NextRequest, extra: Record<string, string>) {
  const out = new Headers()
  const allow = ['content-type', 'accept', 'accept-encoding', 'accept-language', 'user-agent', 'if-none-match']
  for (const [k, v] of req.headers) {
    if (allow.includes(k.toLowerCase())) out.set(k, v)
  }
  for (const [k, v] of Object.entries(extra)) out.set(k, v)
  return out
}

async function handle(
  req: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  // 1) Get FastAPI token from NextAuth JWT
  const jwt = await getToken({ req, secret: NEXTAUTH_SECRET })
  const apiToken = jwt?.apiToken

  if (!apiToken) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 })
  }

  // 2) Build target URL
  const url = new URL(req.url)
  const { path } = await params
  const target = buildTargetUrl(path, url)

  // 3) Prepare method/body/headers
  const method = req.method.toUpperCase()
  const hasBody = !['GET', 'HEAD'].includes(method)
  const body = hasBody ? await req.arrayBuffer() : undefined

  const headers = forwardableHeaders(req, {
    Authorization: `Bearer ${apiToken}`,
  })

  // 4) Call FastAPI
  const upstream = await fetch(target, {
    method,
    headers,
    body,
    redirect: 'manual',
    cache: 'no-store',
  })

  // 5) Stream/return response as-is (works for JSON, text, images, files)
  const outHeaders = new Headers()

  // Pass through common useful headers; especially content-type for images.
  const pass = [
    'content-type',
    'cache-control',
    'content-disposition',
    'etag',
    'last-modified',
  ]
  for (const name of pass) {
    const val = upstream.headers.get(name)
    if (val) outHeaders.set(name, val)
  }

  // Note: do NOT read .text()/json(); just forward the stream/body directly.
  // For 204/304 upstream.body may be null - NextResponse handles that.
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: outHeaders,
  })
}

// Export methods for all common HTTP verbs
export async function GET(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> })      { return handle(req, ctx) }
export async function POST(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> })     { return handle(req, ctx) }
export async function PUT(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> })      { return handle(req, ctx) }
export async function PATCH(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> })    { return handle(req, ctx) }
export async function DELETE(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> })   { return handle(req, ctx) }
export async function HEAD(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> })     { return handle(req, ctx) }
export async function OPTIONS(req: NextRequest, ctx: { params: Promise<{ path?: string[] }> })  { return handle(req, ctx) }
