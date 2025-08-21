'use client'

import { useEffect, useState } from 'react'
import UserItem from '@/components/auth/UserItem'
import AppMenu from '@/components/layout/AppMenu'

export default function Sidebar() {
  const [isVisible, setIsVisible] = useState(false)

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

  return (
    <div className='fixed top-0 left-0 flex flex-col gap-4 w-[250px] h-screen p-4 justify-between overflow-hidden border-r bg-background z-40'>
      {/* User section at top */}
      <div>
        <UserItem />
      </div>

      {/* Navigation menu */}
      <div className='flex-1'>
        <AppMenu />
      </div>
    </div>
  )
}