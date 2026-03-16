'use client'

import { useEffect, useState, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { CheckCircle, XCircle, Loader2 } from 'lucide-react'
import Link from 'next/link'
import BackgroundMesh from '@/components/components/BackgroundMesh'

function VerifyEmailContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')

  useEffect(() => {
    const token = searchParams.get('token')

    if (!token) {
      setStatus('error')
      setMessage('No verification token provided.')
      return
    }

    async function verifyToken() {
      try {
        const res = await fetch(`/api/verify-email?token=${encodeURIComponent(token!)}`)
        const data = await res.json()

        if (res.ok) {
          setStatus('success')
          setMessage(data.message || 'Email verified successfully!')
          setEmail(data.email || '')
          
          // Redirect to sign in after 3 seconds
          setTimeout(() => {
            router.push('/auth/signin')
          }, 3000)
        } else {
          setStatus('error')
          setMessage(data.detail || 'Verification failed. The token may be invalid or expired.')
        }
      } catch {
        setStatus('error')
        setMessage('Network error. Please try again.')
      }
    }

    verifyToken()
  }, [searchParams, router])

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
            {status === 'loading' && (
              <Loader2 className='h-16 w-16 text-primary animate-spin' />
            )}
            {status === 'success' && (
              <CheckCircle className='h-16 w-16 text-green-600 dark:text-green-400' />
            )}
            {status === 'error' && (
              <XCircle className='h-16 w-16 text-red-600 dark:text-red-400' />
            )}
          </div>

          <CardTitle className='text-2xl'>
            {status === 'loading' && 'Verifying Email...'}
            {status === 'success' && 'Email Verified!'}
            {status === 'error' && 'Verification Failed'}
          </CardTitle>
        </CardHeader>

        <CardContent className='space-y-6'>
          {/* Status Message */}
          {status === 'loading' && (
            <div className='text-center text-muted-foreground'>
              <p>Please wait while we verify your email address...</p>
            </div>
          )}

          {status === 'success' && (
            <div className='space-y-4'>
              <div className='bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-md p-4'>
                <p className='text-sm text-green-800 dark:text-green-200 text-center'>
                  {message}
                </p>
                {email && (
                  <p className='text-xs text-green-700 dark:text-green-300 text-center mt-2'>
                    {email}
                  </p>
                )}
              </div>

              <div className='text-center text-sm text-muted-foreground'>
                <p>Your account is now active. You can sign in and start using the Catalog of Second Chances.</p>
                <p className='mt-2 text-xs'>Redirecting to sign in page in 3 seconds...</p>
              </div>

              <Link href='/auth/signin' className='block'>
                <Button className='w-full'>
                  Go to Sign In
                </Button>
              </Link>
            </div>
          )}

          {status === 'error' && (
            <div className='space-y-4'>
              <div className='bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded-md p-4'>
                <p className='text-sm text-red-800 dark:text-red-200 text-center'>
                  {message}
                </p>
              </div>

              <div className='text-center text-sm text-muted-foreground'>
                <p>This could happen if:</p>
                <ul className='list-disc list-inside mt-2 space-y-1 text-left max-w-xs mx-auto'>
                  <li>The verification link has expired (24 hours)</li>
                  <li>The token is invalid or has already been used</li>
                  <li>Your email is already verified</li>
                </ul>
              </div>

              <div className='flex flex-col gap-3'>
                <Link href='/auth/verification-pending' className='block'>
                  <Button variant='default' className='w-full'>
                    Request New Verification Email
                  </Button>
                </Link>
                <Link href='/auth/signin' className='block'>
                  <Button variant='outline' className='w-full'>
                    Try Signing In
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={
      <div className='relative flex min-h-[70vh] md:min-h-[88vh] items-center justify-center'>
        <Loader2 className='h-16 w-16 text-primary animate-spin' />
      </div>
    }>
      <VerifyEmailContent />
    </Suspense>
  )
}

