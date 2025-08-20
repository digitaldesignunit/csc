'use client'

import { useState, useTransition } from 'react'
import { signIn } from 'next-auth/react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

function toSafePathClient(raw: string): string {
  const fallback = '/components'
  try {
    // Build absolute URL to validate origin, but only return path
    const u = new URL(raw, window.location.origin)
    if (u.origin === window.location.origin && u.pathname.startsWith('/')) {
      return u.pathname + u.search + u.hash
    }
  } catch {
    // ignore
  }
  // If it was already a plain path like "/components", keep it
  if (raw.startsWith('/')) return raw
  return fallback
}

export default function SignInForm({ callbackUrl }: { callbackUrl: string }) {
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    const safeCallback = typeof window === 'undefined'
      ? callbackUrl // SSR fallback (already sanitized on server)
      : toSafePathClient(callbackUrl)

    startTransition(async () => {
      await signIn('credentials', {
        redirect: true,  // let NextAuth navigate
        callbackUrl: safeCallback,
        identifier,
        password,
      })
      // no manual router.push needed
    })
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign In</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="identifier">Email or Username</Label>
              <Input
                id="identifier"
                type="text"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={isPending} className="w-full">
              {isPending ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
