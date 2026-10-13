// app/api/auth/[...nextauth]/route.ts
export const runtime = 'nodejs'

import NextAuth, { type AuthOptions } from 'next-auth'
import CredentialsProvider from 'next-auth/providers/credentials'
import { CSC_CLIENT_HEADERS } from '@/lib/cscClient'
import { forwardedFor } from '@/lib/clientAddress'
import { signInWithBackend, type AuthorizedUser } from '@/lib/signIn'
import type { JWT } from 'next-auth/jwt'
import type { Session } from 'next-auth'

// Env
const NEXTAUTH_SECRET = process.env.NEXTAUTH_SECRET!
const FASTAPI_URL = process.env.FASTAPI_URL!

// Types
type AuthorizedUserPayload = AuthorizedUser

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

// Credentials authorize: the backend is the only verifier (decision 8.144 f)
async function authorizeUser(
  credentials?: { identifier: string; password: string },
  request?: { headers?: Record<string, string | string[] | undefined> },
): Promise<AuthorizedUserPayload | null> {
  return signInWithBackend(credentials, {
    fetch,
    backendUrl: FASTAPI_URL,
    headers: {
      ...CSC_CLIENT_HEADERS,
      // the visitor's address, for the backend's login limit
      ...forwardedFor(request?.headers ?? {}),
    },
    log: (message) => console.error(message),
    now: Date.now,
  })
}

// NextAuth options
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
  session: {
    strategy: 'jwt',
    maxAge: 24 * 60 * 60, // 24 hours session max age
    updateAge: 2 * 60 * 60, // Update session every 2 hours
  },
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

      // Invalidate expired API token on subsequent requests (no refresh flow)
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
