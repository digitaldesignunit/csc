'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Home, Package, Search, Palette, Award, FileText } from 'lucide-react'

export default function AppMenu() {
  const router = useRouter()
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const checkScreenSize = () => {
      setIsMobile(window.innerWidth < 768)
    }

    // Check initial size
    checkScreenSize()

    // Add resize listener
    window.addEventListener('resize', checkScreenSize)
    
    return () => window.removeEventListener('resize', checkScreenSize)
  }, [])

  const handleNavigation = (path: string) => {
    router.push(path)
    // Close mobile menu on navigation
    if (isMobile) {
      document.dispatchEvent(new CustomEvent('closeMobileMenu'))
    }
  }

  return (
    <div className="space-y-2">
      {/* Main Navigation */}
      <div className="rounded-lg bg-popover text-popover-foreground p-1">
        <div
          onClick={() => handleNavigation('/')}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <Home className="h-4 w-4" />
          Home
        </div>
        <div
          onClick={() => handleNavigation('/components')}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <Package className="h-4 w-4" />
          Components
        </div>
        <div
          onClick={() => handleNavigation('/findcomponent')}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <Search className="h-4 w-4" />
          Find Component
        </div>
        <div
          onClick={() => handleNavigation('/designs')}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <Palette className="h-4 w-4" />
          Designs
        </div>
      </div>

      {/* Misc Navigation */}
      <div className="rounded-lg bg-popover text-popover-foreground p-1">
        <div
          onClick={() => handleNavigation('/credits')}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <Award className="h-4 w-4" />
          Credits
        </div>
        <div
          onClick={() => handleNavigation('/imprint')}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
        >
          <FileText className="h-4 w-4" />
          Imprint
        </div>
      </div>
    </div>
  )
}
