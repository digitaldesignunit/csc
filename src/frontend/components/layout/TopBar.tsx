'use client'

/**
 * The slim top bar of the navigation shell (decision 8.29): the sidebar
 * toggle, the page title and, on phones, a Scan & Identify shortcut.
 */
import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'
import { useSession } from 'next-auth/react'
import { ScanQrCode } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { pageTitle } from '@/lib/navigation'

export default function TopBar({ betaBannerText }: { betaBannerText?: string }) {
  const pathname = usePathname() ?? '/'
  const search = useSearchParams() ?? new URLSearchParams()
  const { data: session } = useSession()
  const signedIn = Boolean(session?.user) && !(session as { error?: string } | null)?.error
  const title = pageTitle(pathname, search) || 'Catalog of Second Chances'

  return (
    <header className="sticky top-0 z-30 flex h-11 shrink-0 items-center gap-2 border-b bg-background/95 px-2 backdrop-blur supports-[backdrop-filter]:bg-background/60 md:px-3">
      <SidebarTrigger />
      <div aria-hidden className="h-4 w-px bg-border" />
      <h1 className="min-w-0 flex-1 truncate text-sm font-semibold">{title}</h1>
      {betaBannerText ? (
        // the sidebar shows it on wider screens
        <Badge className="shrink-0 border-amber-600 bg-amber-500 px-1.5 py-0 text-[10px] font-bold text-amber-950 md:hidden dark:border-amber-300 dark:bg-amber-400">
          {betaBannerText}
        </Badge>
      ) : null}
      {signedIn && pathname !== '/identify' && (
        <Link
          href="/identify"
          aria-label="Scan & Identify"
          title="Scan & Identify"
          className="inline-flex size-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none md:hidden"
        >
          <ScanQrCode className="size-4" />
        </Link>
      )}
    </header>
  )
}
