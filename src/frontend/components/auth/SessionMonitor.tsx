'use client'

import { useSession, signOut } from 'next-auth/react'
import { useCallback, useEffect, useRef } from 'react'
import { usePageView } from '@/lib/pageView'
import { forgetRecentComponents } from '@/lib/recentComponents'
import { expiredSignInUrl, expiryOutcome } from '@/lib/sessionExpiry'

export default function SessionMonitor() {
  const { data: session, status } = useSession()
  const pageView = usePageView()
  const hasLoggedOut = useRef(false)

  // The session ended. A public view of a component page stays on screen, signed out and drawn
  // again as an anonymous visitor sees it (8.182 a); every other page signs the user out and
  // goes to sign-in, returning to the same address (issue 35).
  const logOut = useCallback((userId: string | undefined) => {
    hasLoggedOut.current = true
    forgetRecentComponents(userId)
    const { pathname, search, hash } = window.location
    if (expiryOutcome(pathname, pageView) === 'anonymous') {
      // a reload, not `router.refresh()`: the cards that load their own data (the records, the
      // History graph with its people) would keep what they hold for the signed-in user
      void signOut({ redirect: false }).then(() => window.location.reload())
      return
    }
    void signOut({
      callbackUrl: expiredSignInUrl(pathname, search, hash),
      redirect: true,
    })
  }, [pageView])

  useEffect(() => {
    // Only process if session is loaded and we haven't already logged out
    if (status === 'loading' || hasLoggedOut.current) return

    // Check if session has expired API token
    if (session?.error === 'ApiTokenExpired') {
      console.log('[SessionMonitor] API token expired, logging out user')
      logOut(session?.user?.id)
    }
  }, [session, status, logOut])

  // Also check session expiry periodically for edge cases
  useEffect(() => {
    if (status === 'loading' || !session || hasLoggedOut.current) return

    const checkSessionExpiry = () => {
      if (hasLoggedOut.current) return
      // Check if we have an API expiry time and it's passed
      if (session.api?.expiresAt && Date.now() >= session.api.expiresAt) {
        console.log('[SessionMonitor] API token expired (periodic check), logging out user')
        logOut(session?.user?.id)
      }
    }

    // Check every 30 seconds
    const interval = setInterval(checkSessionExpiry, 30 * 1000)

    return () => clearInterval(interval)
  }, [session, status, logOut])

  return null // This component renders nothing
}
