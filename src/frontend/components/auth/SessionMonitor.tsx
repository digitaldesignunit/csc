'use client'

import { useSession, signOut } from 'next-auth/react'
import { useEffect, useRef } from 'react'

export default function SessionMonitor() {
  const { data: session, status } = useSession()
  const hasLoggedOut = useRef(false)

  useEffect(() => {
    // Only process if session is loaded and we haven't already logged out
    if (status === 'loading' || hasLoggedOut.current) return

    // Check if session has expired API token
    if (session?.error === 'ApiTokenExpired') {
      console.log('[SessionMonitor] API token expired, logging out user')
      hasLoggedOut.current = true
      
      signOut({ 
        callbackUrl: '/auth/signin?error=SessionExpired',
        redirect: true 
      })
    }
  }, [session, status])

  // Also check session expiry periodically for edge cases
  useEffect(() => {
    if (status === 'loading' || !session || hasLoggedOut.current) return

    const checkSessionExpiry = () => {
      // Check if we have an API expiry time and it's passed
      if (session.api?.expiresAt && Date.now() >= session.api.expiresAt) {
        console.log('[SessionMonitor] API token expired (periodic check), logging out user')
        hasLoggedOut.current = true
        
        signOut({ 
          callbackUrl: '/auth/signin?error=SessionExpired',
          redirect: true 
        })
      }
    }

    // Check every 30 seconds
    const interval = setInterval(checkSessionExpiry, 30 * 1000)

    return () => clearInterval(interval)
  }, [session, status])

  return null // This component renders nothing
}
