// app/api/auth/[...nextauth]/route.ts
export const runtime = 'nodejs'

import NextAuth, { type AuthOptions } from 'next-auth'
import CredentialsProvider from 'next-auth/providers/credentials'
import { MongoClient, type Collection, type WithId } from 'mongodb'
import bcrypt from 'bcryptjs'
import type { JWT } from 'next-auth/jwt'
import type { Session } from 'next-auth'

// ───────────────────────────────────────────────────────────────────────────────
// Env
// ───────────────────────────────────────────────────────────────────────────────
const MONGODB_URI = process.env.MONGODB_URI!
const DB_NAME = process.env.MONGODB_DB!
const DB_USERCOLLECTION = process.env.MONGODB_USERCOLLECTION!
const NEXTAUTH_SECRET = process.env.API_SECRET
const FASTAPI_URL = process.env.FASTAPI_URL!

// Optional fallback if FastAPI doesn’t return expires_in and token has no exp
const FALLBACK_ACCESS_TTL_SECS = Number(process.env.FASTAPI_ACCESS_TOKEN_TTL_SECS ?? 3600)

// ───────────────────────────────────────────────────────────────────────────────
// Types
// ───────────────────────────────────────────────────────────────────────────────
type DBUser = {
  _id: unknown
  username: string
  email?: string
  full_name?: string
  role?: string
  disabled?: boolean
  hashed_password?: string
}

type AuthorizedUserPayload = {
  id: string
  name?: string
  email?: string
  username: string
  role: string
  apiToken: string
  apiTokenExpiresAt: number
}

type CustomJWT = JWT & {
  role?: string
  username?: string
  apiToken?: string
  apiTokenExpiresAt?: number
  error?: 'ApiTokenExpired'
}

type SessionUserPatch = {
  user?: {
    id?: string
    role?: string
    username?: string
  }
  api?: {
    hasAccessToken: boolean
    expiresAt: number
  }
  error?: 'ApiTokenExpired'
}

// ───────────────────────────────────────────────────────────────────────────────
// Mongo singleton (safe for RSC/route handlers)
// ───────────────────────────────────────────────────────────────────────────────
declare global {
  var _mongoClientPromise: Promise<MongoClient> | undefined
}
let client: MongoClient

function errorToString(err: unknown): string {
  if (err instanceof Error) return err.message
  try {
    return JSON.stringify(err)
  } catch {
    return String(err)
  }
}

async function getClient(): Promise<MongoClient> {
  try {
    if (!global._mongoClientPromise) {
      client = new MongoClient(MONGODB_URI)
      global._mongoClientPromise = client.connect()
    }
    client = await global._mongoClientPromise
    return client
  } catch (err: unknown) {
    console.error('[NextAuth][Mongo] Failed to connect:', errorToString(err))
    throw err
  }
}

// ───────────────────────────────────────────────────────────────────────────────
/** Best-effort decode of JWT `exp` (seconds) → ms timestamp. No verification. */
// ───────────────────────────────────────────────────────────────────────────────
function decodeJwtExpMs(token: string): number | undefined {
  try {
    const parts = token.split('.')
    if (parts.length < 2) return
    const payloadB64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const pad = payloadB64.length % 4
    const padded = pad ? payloadB64 + '='.repeat(4 - pad) : payloadB64
    const json = Buffer.from(padded, 'base64').toString('utf8')
    const payload = JSON.parse(json) as { exp?: number }
    if (typeof payload.exp === 'number') return payload.exp * 1000
  } catch {
    // ignore
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// Credentials authorize (Mongo + bcrypt), then exchange for FastAPI token
// ───────────────────────────────────────────────────────────────────────────────
async function authorizeUser(credentials?: { identifier: string; password: string }): Promise<AuthorizedUserPayload | null> {
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
  let usersColl: Collection<DBUser>
  try {
    usersColl = mongo.db(DB_NAME).collection<DBUser>(DB_USERCOLLECTION)
  } catch (err: unknown) {
    console.error('[NextAuth][Mongo] Invalid DB or collection name', {
      DB_NAME,
      DB_USERCOLLECTION,
      error: errorToString(err),
    })
    return null
  }

  // 3) Find user by username OR email
  let user: WithId<DBUser> | null = null
  try {
    user = await usersColl.findOne({
      $or: [{ username: identifier }, { email: lowerEmail }],
      disabled: { $ne: true },
    })
  } catch (err: unknown) {
    console.error('[NextAuth][Mongo] findOne failed:', errorToString(err))
    return null
  }

  if (!user) {
    console.error('[NextAuth][Auth] User not found or disabled', { identifier })
    return null
  }

  if (typeof user.hashed_password !== 'string' || user.hashed_password.length === 0) {
    console.error('[NextAuth][Auth] User record missing hashed_password', { _id: String(user._id) })
    return null
  }

  // 4) Compare password
  let ok = false
  try {
    ok = await bcrypt.compare(password, user.hashed_password)
  } catch (err: unknown) {
    console.error('[NextAuth][Auth] bcrypt.compare failed:', errorToString(err))
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
  } catch (e: unknown) {
    console.error('[NextAuth] Failed to reach FASTAPI_URL/auth/token', FASTAPI_URL, errorToString(e))
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
  } catch (e: unknown) {
    console.error('[NextAuth] FastAPI /auth/token JSON parse failed:', errorToString(e))
    return null
  }

  if (!apiToken) {
    console.error('[NextAuth] FastAPI /auth/token returned no access_token')
    return null
  }

  // Compute absolute expiry in ms
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
    apiToken,
    apiTokenExpiresAt,
  }
}

// ───────────────────────────────────────────────────────────────────────────────
// NextAuth Options
// ───────────────────────────────────────────────────────────────────────────────
const authOptions: AuthOptions = {
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
      const t = token as CustomJWT

      // On sign-in
      if (user) {
        const u = user as unknown as AuthorizedUserPayload
        t.sub = u.id
        t.role = u.role ?? 'user'
        t.username = u.username
        t.email = u.email
        t.apiToken = u.apiToken
        t.apiTokenExpiresAt = u.apiTokenExpiresAt
        t.error = undefined
        return t
      }

      // If we have an access token with an expiry, invalidate it when expired (no refresh flow)
      if (t.apiToken && t.apiTokenExpiresAt) {
        const bufferMs = 60_000 // 60s safety buffer
        if (Date.now() >= Number(t.apiTokenExpiresAt) - bufferMs) {
          t.apiToken = undefined
          t.apiTokenExpiresAt = 0
          t.error = 'ApiTokenExpired'
        }
      }

      return t
    },
    async session({ session, token }) {
      const t = token as CustomJWT
      const s = session as Session & SessionUserPatch

      // never expose apiToken to the browser session
      if (s.user) {
        s.user.id = (t.sub as string | undefined) ?? s.user.id
        s.user.role = t.role ?? s.user.role
        s.user.username = t.username ?? s.user.username
      } else {
        s.user = {
          id: (t.sub as string | undefined) ?? undefined,
          role: t.role ?? 'user',
          username: t.username ?? undefined,
          name: session.user?.name,
          email: session.user?.email ?? undefined,
          image: session.user?.image,
        }
      }

      s.api = {
        hasAccessToken: Boolean(t.apiToken),
        expiresAt: t.apiTokenExpiresAt ?? 0,
      }
      s.error = t.error

      return s
    },
  },
  debug: process.env.NODE_ENV === 'development',
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }
