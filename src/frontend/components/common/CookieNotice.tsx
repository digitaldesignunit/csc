'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Cookie, X } from 'lucide-react'

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
      <Card className="mx-auto max-w-xl border shadow-md bg-background/95 backdrop-blur-sm pointer-events-auto">
        <CardContent className="p-2.5">
          <div className="flex items-center gap-2">
            <Cookie className="h-4 w-4 text-amber-600 flex-shrink-0" />
            <p className="text-xs text-muted-foreground flex-1 leading-snug">
              <span className="font-semibold text-foreground">Can I has cookie?</span>
              {' '}We only use technically necessary cookies. Since this might change in the future, I am asking you, pretty please?
            </p>
            <Button
              size="sm"
              onClick={handleAccept}
              className="h-7 px-2.5 text-xs bg-amber-600 hover:bg-amber-700 flex-shrink-0"
            >
              Accept
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleDismiss}
              className="h-7 w-7 flex-shrink-0"
              aria-label="Dismiss cookie notice"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
