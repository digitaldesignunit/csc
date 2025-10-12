'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { Home, Package, Search, Palette, Award, FileText, User, Shield, QrCode, Terminal, Box } from 'lucide-react'

export default function AppMenu() {
  const router = useRouter()
  const { data: session } = useSession()
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
    <div className="space-y-4">
      {/* MAIN Section */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-muted-foreground px-3 uppercase tracking-wider">
          Main
        </h3>
        <div className="rounded-lg bg-popover text-popover-foreground p-1 border">
          <div
            onClick={() => handleNavigation('/')}
            className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
          >
            <Home className="h-4 w-4" />
            Home / About
          </div>
          
          {/* Dashboard and GH Interface - Only visible to logged in users with valid sessions */}
          {session && !session.error && (
            <>
              <div
                onClick={() => handleNavigation('/dashboard')}
                className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
              >
                <User className="h-4 w-4" />
                Dashboard
              </div>
              
              <div
                onClick={() => handleNavigation('/gh-interface')}
                className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
              >
                <Terminal className="h-4 w-4" />
                GH Interface
              </div>
            </>
          )}
        </div>
      </div>

      {/* COMPONENTS Section - Only visible to logged in users */}
      {session && !session.error && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground px-3 uppercase tracking-wider">
            Components
          </h3>
          <div className="rounded-lg bg-popover text-popover-foreground p-1 border">
            <div
              onClick={() => handleNavigation('/components')}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
            >
              <Package className="h-4 w-4" />
              Browse Components
            </div>
            <div
              onClick={() => handleNavigation('/findcomponent')}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
            >
              <Search className="h-4 w-4" />
              Find Component
            </div>
            <div
              onClick={() => handleNavigation('/identify')}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
            >
              <QrCode className="h-4 w-4" />
              Identify Component
            </div>
          </div>
        </div>
      )}

      {/* DESIGNS Section - Only visible to logged in users */}
      {session && !session.error && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground px-3 uppercase tracking-wider">
            Designs
          </h3>
          <div className="rounded-lg bg-popover text-popover-foreground p-1 border">
            <div
              onClick={() => handleNavigation('/designs')}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
            >
              <Palette className="h-4 w-4" />
              Designs
            </div>
          </div>
        </div>
      )}

      {/* Admin Navigation - Only visible to admin users */}
      {session?.user?.role === 'admin' && (
        <div className="space-y-2">
          <h3 className="text-xs font-semibold text-muted-foreground px-3 uppercase tracking-wider">
            Admin
          </h3>
          <div className="rounded-lg bg-popover text-popover-foreground p-1 border">
            <div
              onClick={() => handleNavigation('/admin/validation')}
              className="flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer"
            >
              <Shield className="h-4 w-4" />
              Component Validation
            </div>
          </div>
        </div>
      )}

      {/* OTHER Section */}
      <div className="space-y-2">
        <h3 className="text-xs font-semibold text-muted-foreground px-3 uppercase tracking-wider">
          Other
        </h3>
        <div className="rounded-lg bg-popover text-popover-foreground p-1 border">
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
    </div>
  )
}
