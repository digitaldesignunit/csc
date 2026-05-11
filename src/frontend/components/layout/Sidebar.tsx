'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useTheme } from 'next-themes'
import UserItem from '@/components/auth/UserItem'
import AppMenu from '@/components/layout/AppMenu'
import { resolveStatic } from '@/lib/utils'

export default function Sidebar() {
  const [isVisible, setIsVisible] = useState(false)
  const { theme, systemTheme } = useTheme()
  const [mounted, setMounted] = useState(false)
  const [showTopFade, setShowTopFade] = useState(false)
  const [showFade, setShowFade] = useState(false)
  const navRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    const checkScreenSize = () => {
      setIsVisible(window.innerWidth >= 768) // md breakpoint
    }
    checkScreenSize()
    window.addEventListener('resize', checkScreenSize)
    return () => window.removeEventListener('resize', checkScreenSize)
  }, [])

  const updateFade = useCallback(() => {
    const el = navRef.current
    if (!el) return
    setShowTopFade(el.scrollTop > 4)
    setShowFade(el.scrollHeight - el.scrollTop - el.clientHeight > 4)
  }, [])

  // Re-evaluate whenever layout/content may change
  useEffect(() => {
    const el = navRef.current
    if (!el) return
    updateFade()
    el.addEventListener('scroll', updateFade)

    const ro = new ResizeObserver(updateFade)
    ro.observe(el)

    return () => {
      el.removeEventListener('scroll', updateFade)
      ro.disconnect()
    }
  }, [updateFade, isVisible])

  if (!isVisible) return null

  const currentTheme = theme === 'system' ? systemTheme : theme
  const isDark = currentTheme === 'dark'
  const logoSrc = isDark ? resolveStatic('/logo/ddu_logo_white.png') : resolveStatic('/logo/ddu_logo_black.png')

  // Dark mode: white-tinted shadow (black-on-black is invisible).
  // Light mode: dark shadow.
  const shadowColor   = isDark ? 'rgba(255,255,255,0.22)' : 'rgba(0,0,0,0.18)'
  const shadowColorMid = isDark ? 'rgba(255,255,255,0.09)' : 'rgba(0,0,0,0.06)'
  const topShadow    = `linear-gradient(to bottom, ${shadowColor} 0%, ${shadowColorMid} 50%, transparent 100%)`
  const bottomShadow = `linear-gradient(to top,    ${shadowColor} 0%, ${shadowColorMid} 50%, transparent 100%)`

  return (
    <div className='fixed top-0 left-0 flex flex-col w-[250px] h-screen border-r bg-background z-40 overflow-hidden'>

      {/* Zone 1: Logo + UserItem — pinned */}
      <div className='flex-shrink-0 flex flex-col gap-3 p-2 pt-3'>
        {mounted && (
          <div className='flex justify-center'>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={logoSrc}
              alt="Digital Design Unit"
              width={52}
              height={52}
              className="flex-shrink-0"
              onError={(e) => {
                console.error('Failed to load DDU logo:', logoSrc)
                e.currentTarget.style.display = 'none'
              }}
            />
          </div>
        )}
        <UserItem />
      </div>

      {/* Zone 2: Navigation — scrollable, with bottom fade hint */}
      <div className='relative flex-1 min-h-0'>
        <div
          ref={navRef}
          className='sidebar-scroll h-full overflow-y-auto px-2 py-2'
        >
          <AppMenu />
        </div>

        {/* Top shadow — appears once the user scrolls away from the top */}
        <div
          aria-hidden
          className='pointer-events-none absolute top-0 left-0 right-0 h-14 transition-opacity duration-200'
          style={{ opacity: showTopFade ? 1 : 0, background: topShadow }}
        />

        {/* Bottom shadow — fades out when scrolled to the bottom */}
        <div
          aria-hidden
          className='pointer-events-none absolute bottom-0 left-0 right-0 h-14 transition-opacity duration-200'
          style={{ opacity: showFade ? 1 : 0, background: bottomShadow }}
        />
      </div>


    </div>
  )
}