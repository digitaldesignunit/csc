'use client'

/**
 * Ask for a password reset mail (decision 8.124 a). The answer is the same
 * for every address: nobody learns which ones have an account.
 */
import { useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, KeyRound, Loader2, MailCheck } from 'lucide-react'

import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sent, setSent] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const response = await fetch('/api/password-reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })
      const data = await response.json().catch(() => ({}))
      if (response.status === 202) {
        setSent(data.message ?? 'If an account exists for this address, an email has been sent.')
      } else if (response.status === 429) {
        setError('Too many requests. Please try again in an hour.')
      } else if (response.status === 422) {
        setError('Please enter a valid email address.')
      } else {
        setError('Something went wrong. Please try again.')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative flex min-h-[70vh] items-start justify-center p-4 pt-8 sm:items-center sm:pt-4 md:min-h-[88vh]">
      <BackgroundMesh className="absolute inset-0 -z-10" opacity={0.08} rotationSpeed={0.15} intensity={0.2} />
      <Card className="w-full max-w-md bg-card/75">
        <CardHeader className="text-center">
          <div className="mb-3 flex justify-center">
            {sent ? <MailCheck className="h-12 w-12 text-primary" aria-hidden /> : <KeyRound className="h-12 w-12 text-primary" aria-hidden />}
          </div>
          <CardTitle className="text-2xl">{sent ? 'Check your email' : 'Forgot your password?'}</CardTitle>
          <CardDescription className="text-base">
            {sent
              ? 'The link works once and expires after one hour.'
              : 'Enter the address of your account and we send you a link to choose a new one.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          {sent ? (
            <p role="status" className="rounded-md border border-border bg-muted/40 p-3 text-sm">{sent}</p>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="reset-email">Email address</Label>
                <Input
                  id="reset-email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="your.name@example.org"
                  className="backdrop-blur"
                  required
                />
              </div>
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy || !email.trim()}>
                {busy ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Sending...</> : 'Send the link'}
              </Button>
            </form>
          )}
          <div className="text-center text-sm">
            <Link href="/auth/signin" className="inline-flex items-center gap-1 text-primary hover:underline">
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden />Back to sign in
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
