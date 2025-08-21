'use client'

import { useState, useEffect } from 'react'
import { Menu, X, BookOpenText } from 'lucide-react'
import AppMenu from '@/components/layout/AppMenu'
import ThemeToggle from '@/components/common/ThemeToggle'
import UserItem from '@/components/auth/UserItem'

export default function Header() {
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

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

  return (
    <>
      {/* Main Header */}
      <div className='flex items-center justify-between gap-4 p-4 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60'>
        {/* Left side - Logo and Title */}
        <div className='flex items-center gap-3'>
          <BookOpenText className="h-6 w-6 text-primary" />
          <h1 className='text-xl font-bold text-foreground'>Catalogue of Second Chances</h1>
        </div>

        {/* Right side - Theme toggle and mobile menu button */}
        <div className='flex items-center gap-3'>
          <ThemeToggle />
          
          {/* Mobile menu button */}
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className='md:hidden p-2 rounded-md hover:bg-accent hover:text-accent-foreground transition-colors'
            aria-label="Toggle mobile menu"
          >
            {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile UserItem - shown below header on mobile */}
      {isMobile && (
        <div className='md:hidden p-2 border-b bg-muted/30'>
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