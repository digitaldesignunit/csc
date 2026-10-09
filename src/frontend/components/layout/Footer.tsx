'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useSession } from 'next-auth/react'

import { footerMode } from '@/lib/footer'
import { copyright_year } from '@/lib/utils'

/** The footer by page (decision 8.118 C-4): full on public pages, one thin line in the app, none in forms. */
export default function Footer() {
  const pathname = usePathname() ?? '/'
  const { data: session, status } = useSession()
  const signedIn = status === 'authenticated' && !(session as { error?: string } | null)?.error
  const mode = footerMode(pathname, status === 'loading' ? true : signedIn)
  if (mode === 'none') return null

  const link = 'hover:underline text-muted-foreground hover:text-foreground'

  if (mode === 'thin') {
    return (
      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 border-t p-1.5 text-xs">
        <Link href="/imprint" className={link}>Imprint</Link>
        <Link href="/credits" className={link}>Credits</Link>
        <Link href="/settings" className={link}>Cookie settings</Link>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center justify-center gap-2 border-t p-2 text-center text-xs sm:flex-row">
      <p>
        &copy; {copyright_year()} <a href="https://www.researchgate.net/profile/Max-Eschenbach" target="_blank" rel="noreferrer" className="hover:underline">Max Benjamin Eschenbach</a>
        {' '}&bull; powered by{' '}
        <a href="https://www.dg.architektur.tu-darmstadt.de/" target="_blank" rel="noreferrer" className="hover:underline">Digital Design Unit (DDU)</a>
      </p>
      <nav aria-label="Legal" className="flex gap-3">
        <Link href="/imprint" className={link}>Imprint</Link>
        <Link href="/credits" className={link}>Credits</Link>
        <Link href="/settings" className={link}>Cookie settings</Link>
      </nav>
    </div>
  )
}
