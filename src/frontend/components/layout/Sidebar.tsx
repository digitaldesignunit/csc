'use client'

import { useEffect, useState } from 'react'
import { useTheme } from 'next-themes'
import UserItem from '@/components/auth/UserItem'
import AppMenu from '@/components/layout/AppMenu'
import { resolveStatic } from '@/lib/utils'

export default function Sidebar() {
  const [isVisible, setIsVisible] = useState(false)
  const { theme, systemTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  useEffect(() => {
    const checkScreenSize = () => {
      setIsVisible(window.innerWidth >= 768) // md breakpoint
    }

    // Check initial size
    checkScreenSize()

    // Add resize listener
    window.addEventListener('resize', checkScreenSize)
    
    return () => window.removeEventListener('resize', checkScreenSize)
  }, [])

  if (!isVisible) return null

  // Determine logo based on theme
  const currentTheme = theme === 'system' ? systemTheme : theme
  const isDark = currentTheme === 'dark'
  const logoSrc = isDark ? resolveStatic('/logo/ddu_logo_white.png') : resolveStatic('/logo/ddu_logo_black.png')

  return (
    <div className='fixed top-0 left-0 flex flex-col gap-2 w-[250px] h-screen p-2 justify-between overflow-hidden border-r bg-background z-40'>
      {/* DDU Logo and User section at top */}
      <div className='flex flex-col gap-3'>
        {mounted && (
          <div className='flex justify-center'>
            <img
              src={logoSrc}
              alt="Digital Design Unit"
              width={56}
              height={56}
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

      {/* Navigation menu */}
      <div className='flex-1'>
        <AppMenu />
      </div>
    </div>
  )
}