'use client'

import { useState, useTransition, useEffect } from 'react'
import { signIn } from 'next-auth/react'
import { useSearchParams } from 'next/navigation'
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
  const [focusedField, setFocusedField] = useState<string | null>(null)
  const searchParams = useSearchParams()

  // Check for error messages in URL (from NextAuth redirects)
  useEffect(() => {
    const errorParam = searchParams.get('error')
    if (errorParam) {
      switch (errorParam) {
        case 'CredentialsSignin':
          setError('Invalid email/username or password. Please try again.')
          break
        case 'AccessDenied':
          setError('Access denied. Please check your credentials.')
          break
        case 'Verification':
          setError('Please verify your email address before signing in.')
          break
        case 'Configuration':
          setError('Authentication service is not properly configured.')
          break
        case 'SessionExpired':
          setError('Your session has expired. Please sign in again.')
          break
        case 'Default':
          setError('An error occurred during sign in. Please try again.')
          break
        default:
          setError('Sign in failed. Please try again.')
      }
    }
  }, [searchParams])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    
    // Client-side validation
    if (!identifier.trim()) {
      setError('Please enter your email or username.')
      return
    }
    if (!password.trim()) {
      setError('Please enter your password.')
      return
    }
    
    const safeCallback = typeof window === 'undefined'
      ? callbackUrl // SSR fallback (already sanitized on server)
      : toSafePathClient(callbackUrl)

    startTransition(async () => {
      const result = await signIn('credentials', {
        redirect: false, // Don't redirect automatically so we can handle errors
        callbackUrl: safeCallback,
        identifier: identifier.trim(),
        password,
      })

      if (result?.error) {
        // Handle specific error cases
        switch (result.error) {
          case 'CredentialsSignin':
            setError('Invalid email/username or password. Please check your credentials and try again.')
            break
          case 'AccessDenied':
            setError('Access denied. Please contact an administrator if you believe this is an error.')
            break
          case 'Verification':
            setError('Please verify your email address before signing in.')
            break
          case 'Configuration':
            setError('Authentication service is not properly configured. Please try again later.')
            break
          default:
            setError('Sign in failed. Please try again or contact support if the problem persists.')
        }
      } else if (result?.ok) {
        // Successful sign in, redirect manually
        window.location.href = safeCallback
      }
    })
  }

  return (
    <div className="flex min-h-[70vh] md:min-h-[88vh] items-start sm:items-center justify-center p-4 pt-8 sm:pt-4">
      <Card className="w-full max-w-md bg-card/75">
        <CardHeader>
          <CardTitle>Sign In</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="gap-1 flex flex-col">
              <Label htmlFor="identifier">Email or Username</Label>
              <Input
                id="identifier"
                type="text"
                className="backdrop-blur placeholder:opacity-40"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                onFocus={() => setFocusedField('identifier')}
                onBlur={() => setFocusedField(null)}
                placeholder={focusedField === 'identifier' ? '' : 're-usevelt'}
                required
              />
            </div>
            <div className="gap-1 flex flex-col">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                className="backdrop-blur placeholder:opacity-40"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onFocus={() => setFocusedField('password')}
                onBlur={() => setFocusedField(null)}
                placeholder={focusedField === 'password' ? '' : '••••••••••'}
                required
              />
            </div>
            <Button type="submit" disabled={isPending} className="w-full">
              {isPending ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>
          
          <div className="mt-4 text-center text-sm text-muted-foreground">
            Don&apos;t have an account?{' '}
            <a 
              href="/auth/register" 
              className="text-primary hover:underline font-medium"
            >
              Register here
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
