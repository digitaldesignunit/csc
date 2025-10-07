'use client'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Cookie, RotateCcw } from 'lucide-react'
import { useCookieConsent } from '@/hooks/useCookieConsent'

export default function CookieSettingsSection() {
  const { bannerDismissed, showBannerAgain, isLoading } = useCookieConsent()

  const handleShowBannerAgain = () => {
    showBannerAgain()
    // Refresh the page to show the banner
    window.location.reload()
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <Cookie className="h-5 w-5 text-amber-600" />
            <div>
              <CardTitle>🍪 Cookie Information</CardTitle>
              <CardDescription>Information about cookies used on this website</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <Cookie className="h-5 w-5 text-amber-600" />
          <div>
            <CardTitle>🍪 Cookie Information</CardTitle>
            <CardDescription>Information about cookies used on this website</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Current Status */}
        <div className="p-4 bg-green-50 dark:bg-green-950/20 border border-green-200 dark:border-green-800 rounded-lg">
          <h4 className="font-medium mb-2 text-green-800 dark:text-green-200">✅ Privacy-Friendly Approach</h4>
          <p className="text-sm text-green-700 dark:text-green-300">
            We only use technically necessary cookies. No tracking, no analytics, no marketing cookies! 
            Your privacy is protected by default. 🛡️
          </p>
        </div>

        {/* Cookie Information */}
        <div className="space-y-4">
          <div className="p-4 border rounded-lg">
            <div className="flex items-start justify-between mb-2">
              <h4 className="font-medium">Necessary Cookies Only</h4>
              <div className="w-3 h-3 rounded-full bg-green-500" />
            </div>
            <p className="text-sm text-muted-foreground mb-3">
              We only use cookies that are essential for the website to function properly. These include:
            </p>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4">
              <li>• Authentication and session management</li>
              <li>• Security features and CSRF protection</li>
              <li>• Basic functionality and user preferences</li>
              <li>• Theme settings (light/dark mode)</li>
            </ul>
          </div>

          <div className="p-4 border rounded-lg bg-muted/30">
            <h4 className="font-medium mb-2">What We DON'T Use</h4>
            <ul className="text-sm text-muted-foreground space-y-1 ml-4">
              <li>❌ No analytics or tracking cookies</li>
              <li>❌ No advertising or marketing cookies</li>
              <li>❌ No third-party tracking scripts</li>
              <li>❌ No social media tracking pixels</li>
            </ul>
          </div>
        </div>

        {/* Banner Status */}
        <div className="flex items-center justify-between p-4 border rounded-lg">
          <div>
            <h4 className="font-medium mb-1">Cookie Banner</h4>
            <p className="text-sm text-muted-foreground">
              {bannerDismissed 
                ? "You've acknowledged our cookie notice. Want to see it again?" 
                : "The cookie banner is currently visible."}
            </p>
          </div>
          {bannerDismissed && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleShowBannerAgain}
              className="flex items-center gap-2"
            >
              <RotateCcw className="h-4 w-4" />
              Show Banner Again
            </Button>
          )}
        </div>

        {/* Additional Info */}
        <div className="text-xs text-muted-foreground space-y-1 pt-4 border-t">
          <p><strong>Data Storage:</strong> Only banner dismissal status is stored locally.</p>
          <p><strong>Privacy:</strong> No personal data is collected or transmitted via cookies.</p>
          <p><strong>Compliance:</strong> Fully GDPR compliant with minimal data collection.</p>
        </div>
      </CardContent>
    </Card>
  )
}
