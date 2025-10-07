'use client'

import { useState, useEffect } from 'react'

const COOKIE_BANNER_DISMISSED_KEY = 'csc-cookie-banner-dismissed'

export function useCookieConsent() {
  const [bannerDismissed, setBannerDismissed] = useState<boolean | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const loadBannerStatus = () => {
      try {
        const dismissed = localStorage.getItem(COOKIE_BANNER_DISMISSED_KEY)
        setBannerDismissed(dismissed === 'true')
      } catch (error) {
        console.error('Failed to load cookie banner status:', error)
        setBannerDismissed(false)
      } finally {
        setIsLoading(false)
      }
    }

    loadBannerStatus()

    // Listen for storage changes (if user dismisses banner in another tab)
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === COOKIE_BANNER_DISMISSED_KEY) {
        loadBannerStatus()
      }
    }

    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [])

  const dismissBanner = () => {
    setBannerDismissed(true)
    localStorage.setItem(COOKIE_BANNER_DISMISSED_KEY, 'true')
  }

  const showBannerAgain = () => {
    setBannerDismissed(false)
    localStorage.removeItem(COOKIE_BANNER_DISMISSED_KEY)
  }

  return {
    bannerDismissed,
    isLoading,
    dismissBanner,
    showBannerAgain,
    // For backwards compatibility - we only have necessary cookies now
    hasNecessary: true,
    hasAnalytics: false,
    hasMarketing: false,
    hasPreferences: false,
  }
}
