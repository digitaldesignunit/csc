'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Cookie, X } from 'lucide-react'

import { Button } from '@/components/ui/button'

const COOKIE_BANNER_DISMISSED_KEY = 'csc-cookie-banner-dismissed'

export default function CookieNotice() {
  const [showBanner, setShowBanner] = useState(false)

  useEffect(() => {
    // Check if user has already dismissed the banner
    const bannerDismissed = localStorage.getItem(COOKIE_BANNER_DISMISSED_KEY)
    
    if (!bannerDismissed) {
      setShowBanner(true)
    }
  }, [])

  const handleAccept = () => {
    localStorage.setItem(COOKIE_BANNER_DISMISSED_KEY, 'true')
    setShowBanner(false)
  }

  const handleDismiss = () => {
    localStorage.setItem(COOKIE_BANNER_DISMISSED_KEY, 'true')
    setShowBanner(false)
  }

  if (!showBanner) return null

  return (
    <div className="fixed bottom-0 left-0 right-0 z-50 p-2 pointer-events-none">
      <div
        role="region"
        aria-label="Cookies"
        className="pointer-events-auto mx-auto flex max-w-xl items-center gap-2 rounded-lg border bg-background/95 px-2.5 py-1.5 shadow-md backdrop-blur-sm"
      >
        <Cookie className="h-4 w-4 shrink-0 text-amber-600" aria-hidden />
        <p className="flex-1 text-xs leading-snug text-muted-foreground">
          CSC stores only what it needs: your sign-in and the theme.{' '}
          <Link href="/privacy" className="font-medium text-primary underline underline-offset-2">Privacy</Link>
        </p>
        <Button size="sm" onClick={handleAccept} className="h-7 shrink-0 bg-amber-600 px-2.5 text-xs hover:bg-amber-700">
          OK
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={handleDismiss}
          className="h-7 w-7 shrink-0"
          aria-label="Dismiss cookie notice"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  )
}
