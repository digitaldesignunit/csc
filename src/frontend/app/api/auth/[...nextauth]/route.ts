// app/api/auth/[...nextauth]/route.ts
export const runtime = 'nodejs'

import NextAuth, { type AuthOptions } from 'next-auth'
import CredentialsProvider from 'next-auth/providers/credentials'
import { MongoClient } from 'mongodb'
import bcrypt from 'bcryptjs'

const MONGODB_URI = process.env.MONGODB_URI!
const DB_NAME = process.env.MONGODB_DB!
const DB_USERCOLLECTION = process.env.MONGODB_USERCOLLECTION!
const NEXTAUTH_SECRET = process.env.API_SECRET
const FASTAPI_URL = process.env.FASTAPI_URL!

// optional fallback if FastAPI doesn’t return expires_in and token has no exp
const FALLBACK_ACCESS_TTL_SECS = Number(process.env.FASTAPI_ACCESS_TOKEN_TTL_SECS ?? 3600)

// -------- Mongo singleton (safe for RSC/route handlers) --------
declare global {
  // eslint-disable-next-line no-var
  var _mongoClientPromise: Promise<MongoClient> | undefined
}
let client: MongoClient

async function getClient(): Promise<MongoClient> {
  try {
    if (!global._mongoClientPromise) {
      client = new MongoClient(MONGODB_URI)
      global._mongoClientPromise = client.connect()
    }
    client = await global._mongoClientPromise
    return client
  } catch (err: any) {
    console.error('[NextAuth][Mongo] Failed to connect:', err?.message || err)
    throw err
  }
}

// ---- helpers: decode exp from JWT (no verify, best-effort) ----
function decodeJwtExpMs(token: string): number | undefined {
  try {
    const parts = token.split('.')
    if (parts.length < 2) return
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const pad = payloadB64.length % 4
    const padded = pad ? payloadB64 + '='.repeat(4 - pad) : payloadB64
    const json = Buffer.from(padded, 'base64').toString('utf8')
    const payload = JSON.parse(json)
    if (typeof payload.exp === 'number') return payload.exp * 1000
  } catch {
    // ignore
  }
}

// -------- Credentials authorize (Mongo + bcrypt), then exchange for FastAPI token --------
async function authorizeUser(credentials?: { identifier: string; password: string }) {
  if (!credentials) {
    console.error('[NextAuth][Auth] No credentials payload received')
    return null
  }
  const rawIdentifier: unknown = credentials.identifier
  const password: unknown = credentials.password

  if (typeof rawIdentifier !== 'string' || typeof password !== 'string') {
    console.error('[NextAuth][Auth] Invalid credential types', {
      hasIdentifier: typeof rawIdentifier === 'string',
      hasPassword: typeof password === 'string',
    })
    return null
  }

  const identifier = rawIdentifier.trim()
  const lowerEmail = identifier.includes('@') ? identifier.toLowerCase() : identifier

  // 1) Connect to Mongo
  let mongo: MongoClient
  try {
    mongo = await getClient()
  } catch {
    return null
  }

  // 2) Select DB/collection
  let usersColl
  try {
    usersColl = mongo.db(DB_NAME).collection(DB_USERCOLLECTION)
  } catch (err: any) {
    console.error('[NextAuth][Mongo] Invalid DB or collection name', {
      DB_NAME,
      DB_USERCOLLECTION,
      error: err?.message || err,
    })
    return null
  }

  // 3) Find user by username OR email
  let user: any = null
  try {
    user = await usersColl.findOne({
      $or: [{ username: identifier }, { email: lowerEmail }],
      disabled: { $ne: true },
    })
  } catch (err: any) {
    console.error('[NextAuth][Mongo] findOne failed:', err?.message || err)
    return null
  }

  if (!user) {
    console.error('[NextAuth][Auth] User not found or disabled', { identifier })
    return null
  }

  if (!user.hashed_password || typeof user.hashed_password !== 'string') {
    console.error('[NextAuth][Auth] User record missing hashed_password', { _id: String(user._id) })
    return null
  }

  // 4) Compare password
  let ok = false
  try {
    ok = await bcrypt.compare(password, user.hashed_password)
  } catch (err: any) {
    console.error('[NextAuth][Auth] bcrypt.compare failed:', err?.message || err)
    return null
  }
  if (!ok) {
    console.error('[NextAuth][Auth] Password mismatch', { identifier })
    return null
  }

  // 5) Exchange for FastAPI token
  const body = new URLSearchParams()
  body.set('username', user.username)
  body.set('password', password)

  let resp: Response
  try {
    resp = await fetch(`${FASTAPI_URL.replace(/\/+$/, '')}/auth/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Accept: 'application/json',
      },
      body,
      cache: 'no-store',
    })
  } catch (e: any) {
    console.error('[NextAuth] Failed to reach FASTAPI_URL/auth/token', FASTAPI_URL, e?.message || e)
    return null
  }

  if (!resp.ok) {
    const txt = await resp.text().catch(() => '')
    console.error('[NextAuth] FastAPI /auth/token failed', {
      status: resp.status,
      body: txt,
      url: `${FASTAPI_URL}/auth/token`,
      passedUsername: user.username,
    })
    return null
  }

  let apiToken: string | undefined
  let expiresIn: number | undefined
  try {
    const tok = (await resp.json()) as { access_token?: string; token_type?: string; expires_in?: number }
    apiToken = tok?.access_token
    expiresIn = typeof tok?.expires_in === 'number' ? tok.expires_in : undefined
  } catch (e: any) {
    console.error('[NextAuth] FastAPI /auth/token JSON parse failed:', e?.message || e)
    return null
  }

  if (!apiToken) {
    console.error('[NextAuth] FastAPI /auth/token returned no access_token')
    return null
  }

  // compute absolute expiry in ms
  const fromExpClaim = decodeJwtExpMs(apiToken)
  const apiTokenExpiresAt =
    fromExpClaim ??
    (expiresIn ? Date.now() + expiresIn * 1000 : Date.now() + FALLBACK_ACCESS_TTL_SECS * 1000)

  // 6) Return user info for NextAuth to embed into its JWT
  return {
    id: String(user._id),
    name: user.full_name ?? user.username,
    email: user.email,
    username: user.username,
    role: user.role ?? 'user',
    apiToken,                 // stored in NextAuth JWT (server-side)
    apiTokenExpiresAt,        // absolute ms timestamp
  }
}

export const authOptions: AuthOptions = {
  providers: [
    CredentialsProvider({
      name: 'Credentials',
      credentials: {
        identifier: { label: 'Email or Username', type: 'text' },
        password: { label: 'Password', type: 'password' },
      },
      authorize: authorizeUser,
    }),
  ],
  pages: {
    signIn: '/auth/signin',
    error: '/auth/signin',
  },
  session: { strategy: 'jwt' },
  secret: NEXTAUTH_SECRET,
  callbacks: {
    async jwt({ token, user }) {
      const t = token as any

      // on sign-in
      if (user) {
        t.sub = (user as any).id
        t.role = (user as any).role ?? 'user'
        t.username = (user as any).username
        t.email = (user as any).email
        t.apiToken = (user as any).apiToken
        t.apiTokenExpiresAt = (user as any).apiTokenExpiresAt
        t.error = undefined
        return token
      }

      // if we have an access token with an expiry, invalidate it when expired (no refresh flow)
      if (t.apiToken && t.apiTokenExpiresAt) {
        const bufferMs = 60_000 // 60s safety buffer
        if (Date.now() >= Number(t.apiTokenExpiresAt) - bufferMs) {
          t.apiToken = undefined
          t.apiTokenExpiresAt = 0
          t.error = 'ApiTokenExpired'
        }
      }

      return token
    },
    async session({ session, token }) {
      const t = token as any
      // never expose apiToken to the browser session
      if (session.user) {
        ;(session.user as any).id = t.sub as string
        ;(session.user as any).role = (t.role as string) ?? 'user'
        ;(session.user as any).username = t.username as string
      }
      ;(session as any).api = {
        hasAccessToken: Boolean(t.apiToken),
        expiresAt: t.apiTokenExpiresAt ?? 0,
      }
      ;(session as any).error = t.error
      return session
    },
  },
  debug: process.env.NODE_ENV === 'development',
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }
