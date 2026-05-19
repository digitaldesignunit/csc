'use client'

import { useState, useEffect } from 'react'
import { Menu, X } from 'lucide-react'
import { useTheme } from 'next-themes'
import AppMenu from '@/components/layout/AppMenu'
import ThemeToggle from '@/components/common/ThemeToggle'
import UserItem from '@/components/auth/UserItem'
import { Badge } from '@/components/ui/badge'
import { resolveStatic } from '@/lib/utils'

type HeaderProps = {
  betaBannerText?: string
}

export default function Header({ betaBannerText }: HeaderProps) {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const { theme, systemTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    const checkScreenSize = () => {
      const mobile = window.innerWidth < 768
      setIsMobile(mobile)
      if (!mobile && isMobileMenuOpen) {
        setIsMobileMenuOpen(false)
      }
    }

    // Check initial size
    checkScreenSize()

    // Add resize listener
    window.addEventListener('resize', checkScreenSize)
    
    return () => window.removeEventListener('resize', checkScreenSize)
  }, [isMobileMenuOpen])

  // Close mobile menu when navigation items are clicked
  useEffect(() => {
    const handleCloseMobileMenu = () => setIsMobileMenuOpen(false)
    
    document.addEventListener('closeMobileMenu', handleCloseMobileMenu)
    
    return () => {
      document.removeEventListener('closeMobileMenu', handleCloseMobileMenu)
    }
  }, [])

  // Determine logo based on theme
  const currentTheme = theme === 'system' ? systemTheme : theme
  const isDark = currentTheme === 'dark'
  const logoSrc = isDark ? resolveStatic('/logo/ddu_logo_white.png') : resolveStatic('/logo/ddu_logo_black.png')

  return (
    <>
      {/* Main Header */}
      <div className="flex min-h-11 items-center justify-between gap-3 border-b bg-background/95 px-3 py-2 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:min-h-10 md:px-4 md:py-1.5">
        {/* Left side - Logo and Title */}
        <div className="flex min-w-0 items-center gap-2 md:gap-2.5">
          {mounted && isMobile && (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={logoSrc}
              alt="Digital Design Unit"
              width={32}
              height={32}
              className="flex-shrink-0"
              onError={(e) => {
                console.error('Failed to load DDU logo:', logoSrc)
                e.currentTarget.style.display = 'none'
              }}
            />
          )}
          <h1 className="truncate text-base font-semibold leading-snug text-foreground">
            Catalog of Second Chances
          </h1>
          {betaBannerText ? (
            <Badge
              className="shrink-0 overflow-visible border-amber-600 bg-amber-500 px-2.5 py-0.5 text-xs font-bold leading-normal text-amber-950 shadow-sm ring-1 ring-amber-700/25 dark:border-amber-300 dark:bg-amber-400 dark:text-amber-950 dark:ring-amber-200/30"
            >
              {betaBannerText}
            </Badge>
          ) : null}
        </div>

        {/* Right side - Theme toggle and mobile menu button */}
        <div className="flex shrink-0 items-center gap-2">
          <ThemeToggle />
          
          {/* Mobile menu button */}
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="cursor-pointer rounded-md p-1.5 transition-colors hover:bg-accent hover:text-accent-foreground md:hidden"
            aria-label="Toggle mobile menu"
          >
            {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile UserItem - shown below header on mobile */}
      {isMobile && (
        <div className="border-b bg-muted/30 p-1.5 md:hidden">
          <UserItem />
        </div>
      )}

      {/* Mobile Navigation Menu - collapsible */}
      {isMobileMenuOpen && (
        <div className='md:hidden border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 animate-in slide-in-from-top-2 duration-200'>
          <div className='p-2'>
            <AppMenu />
          </div>
        </div>
      )}
    </>
  )
}