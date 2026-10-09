'use client'

/**
 * Choose a new password with the token of the mail (decision 8.124 a). The
 * token works once; a reset signs every other device out, so the next step
 * is the sign-in page.
 */
import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, CheckCircle2, Eye, EyeOff, KeyRound, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PASSWORD_CHANGED_PARAM, PASSWORD_CHANGED_VALUE, passwordProblem } from '@/lib/password'

export default function ResetPasswordForm({ token }: { token: string }) {
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [show, setShow] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const problem = password ? passwordProblem(password) : null
  const mismatch = again.length > 0 && again !== password
  const ready = !!token && password.length > 0 && !problem && again === password

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!ready) return
    setError(null)
    setBusy(true)
    try {
      const response = await fetch('/api/password-reset/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: password }),
      })
      const data = await response.json().catch(() => ({}))
      if (response.ok) {
        setDone(true)
      } else if (response.status === 429) {
        setError('Too many attempts. Please try again in an hour.')
      } else {
        setError(typeof data.detail === 'string'
          ? data.detail
          : 'The password was not accepted. Check the rules and try again.')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  const signIn = `/auth/signin?${PASSWORD_CHANGED_PARAM}=${PASSWORD_CHANGED_VALUE}`
  return (
    <div className="flex min-h-[70vh] items-start justify-center p-4 pt-8 sm:items-center sm:pt-4 md:min-h-[88vh]">
      <Card className="w-full max-w-md bg-card/75">
        <CardHeader className="text-center">
          <div className="mb-3 flex justify-center">
            {done ? <CheckCircle2 className="h-12 w-12 text-primary" aria-hidden /> : <KeyRound className="h-12 w-12 text-primary" aria-hidden />}
          </div>
          <CardTitle className="text-2xl">{done ? 'Password changed' : 'Choose a new password'}</CardTitle>
          <CardDescription className="text-base">
            {done ? 'You are signed out everywhere. Sign in with the new password.'
              : 'It signs you out on every other device.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {done ? (
            <Button asChild className="w-full"><Link href={signIn}>Sign in</Link></Button>
          ) : !token ? (
            <div className="space-y-3 text-sm">
              <p role="alert" className="text-destructive">This link is incomplete. Open the link of the email again, or ask for a new one.</p>
              <Button asChild variant="outline" className="w-full"><Link href="/auth/forgot-password">Ask for a new link</Link></Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="new-password">New password</Label>
                <div className="relative">
                  <Input
                    id="new-password"
                    type={show ? 'text' : 'password'}
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    className="pr-10 backdrop-blur"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShow((value) => !value)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    aria-label={show ? 'Hide the password' : 'Show the password'}
                  >
                    {show ? <EyeOff className="h-4 w-4" aria-hidden /> : <Eye className="h-4 w-4" aria-hidden />}
                  </button>
                </div>
                {problem && <p className="text-xs text-destructive">{problem}</p>}
              </div>
              <div className="space-y-1">
                <Label htmlFor="repeat-password">Repeat the password</Label>
                <Input
                  id="repeat-password"
                  type={show ? 'text' : 'password'}
                  autoComplete="new-password"
                  value={again}
                  onChange={(event) => setAgain(event.target.value)}
                  className="backdrop-blur"
                  required
                />
                {mismatch && <p className="text-xs text-destructive">The two passwords differ.</p>}
              </div>
              {error && (
                <div role="alert" className="space-y-2 text-sm">
                  <p className="text-destructive">{error}</p>
                  <Link href="/auth/forgot-password" className="text-primary hover:underline">Ask for a new link</Link>
                </div>
              )}
              <Button type="submit" className="w-full" disabled={!ready || busy}>
                {busy ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : 'Change the password'}
              </Button>
            </form>
          )}
          {!done && (
            <div className="text-center text-sm">
              <Link href="/auth/signin" className="inline-flex items-center gap-1 text-primary hover:underline">
                <ArrowLeft className="h-3.5 w-3.5" aria-hidden />Back to sign in
              </Link>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
