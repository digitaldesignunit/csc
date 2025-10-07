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
    <div className="fixed bottom-0 left-0 right-0 z-50 p-2">
      <Card className="mx-auto max-w-2xl border-2 shadow-lg bg-background/95 backdrop-blur-sm">
        <CardContent className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2">
            <div className="flex items-center gap-2 flex-1">
              <Cookie className="h-8 w-8 text-amber-600 flex-shrink-0 animate-bounce" />
              <div className="text-sm">
                <p className="font-bold text-lg">🍪 Can I has cookie?</p>
                <p className="text-muted-foreground">
                  We only use technically necessary cookies.
                  Since this might change in the future,
                  I am asking you, pretty please?
                </p>
              </div>
            </div>
            <div className="flex flex-col sm:flex-row gap-1 w-full sm:w-auto">
              <Button
                size="sm"
                onClick={handleAccept}
                className="w-full sm:w-auto bg-amber-600 hover:bg-amber-700"
              >
                🍪 OM NOM NOM!
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleDismiss}
                className="w-full sm:w-auto"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
