'use client'

import { useState } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Mail, CheckCircle, AlertCircle } from 'lucide-react'
import Link from 'next/link'
import BackgroundMesh from '@/components/components/BackgroundMesh'

export default function VerificationPendingPage() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  async function handleResend(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setMessage('')
    setLoading(true)

    try {
      const res = await fetch('/api/resend-verification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      })

      const data = await res.json()

      if (!res.ok) {
        setError(data.error || 'Failed to resend verification email')
      } else {
        setMessage('Verification email sent! Please check your inbox.')
        setEmail('')
      }
    } catch {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className='relative flex min-h-[70vh] md:min-h-[88vh] items-start sm:items-center justify-center p-4 pt-8 sm:pt-4'>
      {/* Background Mesh */}
      <BackgroundMesh
        className='absolute inset-0 -z-10'
        opacity={0.08}
        rotationSpeed={0.15}
        intensity={0.2}
      />

      <Card className='w-full max-w-md bg-card/75'>
        <CardHeader className='text-center'>
          <div className='flex justify-center mb-4'>
            <Mail className='h-16 w-16 text-primary' />
          </div>
          <CardTitle className='text-2xl'>Check Your Email</CardTitle>
          <CardDescription className='text-base'>
            We&apos;ve sent you a verification link
          </CardDescription>
        </CardHeader>

        <CardContent className='space-y-6'>
          {/* Success Message */}
          <div className='bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-4'>
            <div className='flex items-start gap-3'>
              <CheckCircle className='h-5 w-5 text-green-600 dark:text-green-400 mt-0.5 flex-shrink-0' />
              <div className='space-y-1'>
                <p className='text-sm font-medium text-green-900 dark:text-green-100'>
                  Registration Successful!
                </p>
                <p className='text-sm text-green-800 dark:text-green-200'>
                  Please check your email inbox for a verification link. Click the link to activate your account.
                </p>
              </div>
            </div>
          </div>

          {/* Instructions */}
          <div className='space-y-3 text-sm text-muted-foreground'>
            <p>
              <strong>Next steps:</strong>
            </p>
            <ol className='list-decimal list-inside space-y-2 ml-2'>
              <li>Check your email inbox (and spam folder)</li>
              <li>Click the verification link in the email</li>
              <li>Return here to sign in</li>
            </ol>
            <p className='text-xs pt-2'>
              The verification link will expire in <strong>24 hours</strong>.
            </p>
          </div>

          {/* Resend Section */}
          <div className='border-t pt-6'>
            <p className='text-sm text-muted-foreground mb-4'>
              Didn&apos;t receive the email?
            </p>

            <form onSubmit={handleResend} className='space-y-4'>
              <div className='space-y-2'>
                <Label htmlFor='email'>Email Address</Label>
                <Input
                  id='email'
                  type='email'
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder='your.email@tu-darmstadt.de'
                  required
                  className='backdrop-blur'
                />
              </div>

              {message && (
                <div className='bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-3'>
                  <p className='text-sm text-green-800 dark:text-green-200'>
                    {message}
                  </p>
                </div>
              )}

              {error && (
                <div className='bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-md p-3'>
                  <div className='flex items-start gap-2'>
                    <AlertCircle className='h-4 w-4 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0' />
                    <p className='text-sm text-red-800 dark:text-red-200'>
                      {error}
                    </p>
                  </div>
                </div>
              )}

              <Button type='submit' className='w-full' disabled={loading}>
                {loading ? 'Sending...' : 'Resend Verification Email'}
              </Button>
            </form>
          </div>

          {/* Sign In Link */}
          <div className='text-center text-sm text-muted-foreground pt-4 border-t'>
            Already verified?{' '}
            <Link href='/auth/signin' className='text-primary hover:underline font-medium'>
              Sign in here
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

