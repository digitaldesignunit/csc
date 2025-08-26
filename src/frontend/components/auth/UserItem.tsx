'use client'

import { useSession, signIn, signOut } from 'next-auth/react'
import { Button } from '@/components/ui/button'
import Link from 'next/link'


function initialsFrom(name?: string | null, email?: string | null, username?: string | null) {
  if (name) {
    const parts = name.trim().split(/\s+/).slice(0, 2)
    if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  const src = username || email || ''
  const local = src.includes('@') ? src.split('@')[0] : src
  return local.slice(0, 3).toUpperCase()
}

export default function UserItem() {
  const { data: session, status } = useSession()

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-between gap-2 rounded-lg border border-border p-2 animate-pulse bg-card">
        <div className="h-10 w-10 rounded-full bg-muted" />
        <div className="grow">
          <div className="mb-1 h-4 w-32 rounded bg-muted" />
          <div className="h-3 w-48 rounded bg-muted" />
        </div>
      </div>
    )
  }

  if (!session?.user) {
    return (
      <div className="space-y-2">
        <Button
          onClick={() => signIn()}
          className="w-full"
          variant="default"
        >
          Sign in
        </Button>
        <Button
          onClick={() => window.location.href = '/auth/register'}
          className="w-full"
          variant="outline"
        >
          Register
        </Button>
      </div>
    )
  }

  const name = session.user.name ?? ''
  const email = session.user?.email ?? ''
  const username = (session.user as { username?: string | null }).username ?? ''
  const initials = initialsFrom(name, email, username)

  const hasToken = (session as { api?: { hasAccessToken?: boolean } }).api?.hasAccessToken
  const error = (session as { error?: 'ApiTokenExpired' | string }).error
  const isExpired = error === 'ApiTokenExpired' || hasToken === false

  return (
    <div
      className={`rounded-lg border p-2 bg-card ${
        isExpired ? 'border-destructive/40 bg-destructive/10' : 'border-border'
      }`}
    >
      {isExpired ? (
        // Expired session layout - button below info
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            {/* avatar */}
            <div
              className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full font-bold bg-destructive text-destructive-foreground"
              aria-hidden
            >
              {initials}
            </div>

            {/* identity */}
            <div className="grow overflow-hidden">
              <p className="truncate text-sm font-semibold text-foreground">
                {name || username || email}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {email || username}
              </p>
              <p className="mt-0.5 text-xs font-medium text-destructive">
                Session expired
              </p>
              {/* Dashboard Link */}
              <Link href="/dashboard" className="block mt-1">
                <p className="text-xs text-primary hover:text-primary/80 transition-colors cursor-pointer">
                  View Dashboard →
                </p>
              </Link>
            </div>
          </div>
          
          {/* Re-authenticate button below */}
          <Button
            onClick={() => signIn()}
            size="sm"
            variant="destructive"
            title="Re-authenticate"
            className="w-full"
          >
            Re-authenticate
          </Button>
        </div>
      ) : (
        // Normal session layout - button below info
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            {/* avatar */}
            <div
              className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-full font-bold bg-primary text-primary-foreground"
              aria-hidden
            >
              {initials}
            </div>

            {/* identity */}
            <div className="grow overflow-hidden">
              <p className="truncate text-sm font-semibold text-foreground">
                {name || username || email}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {email || username}
              </p>
            </div>
          </div>
          
          {/* Logout button below */}
          <Button
            onClick={() => signOut()}
            size="sm"
            variant="outline"
            title="Sign out"
            className="w-full"
          >
            Logout
          </Button>
        </div>
      )}
    </div>
  )
}
