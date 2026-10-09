'use client'

import { Cookie } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useCookieConsent } from '@/hooks/useCookieConsent'

/** Settings, "Cookies": one sentence and the way back to the notice (decision 8.118 S6). */
export default function CookieSettingsSection() {
  const { showBannerAgain, isLoading } = useCookieConsent()

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Cookie className="h-4 w-4 text-primary" aria-hidden />
          Cookies
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 text-sm">
        <p className="min-w-0 flex-1">
          This site sets only the cookies it needs to work: no tracking, no analytics, no advertising.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isLoading}
          onClick={() => {
            showBannerAgain()
            // the notice reads its state when the page loads
            window.location.reload()
          }}
        >
          Show the cookie notice again
        </Button>
      </CardContent>
    </Card>
  )
}
