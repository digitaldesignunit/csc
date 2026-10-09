'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ShieldAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ADMIN_NOTICE, adminPageNeed } from '@/lib/adminAccess'
import { useMe } from '@/lib/me'

/**
 * Every /admin page: the page opens for those who may, and a caller who may
 * not sees why, instead of being sent away without a word.
 */
export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? '/admin'
  const { me, loading, isAdmin, moderatesAny, reviewsAny } = useMe()
  const need = adminPageNeed(pathname)

  if (!me) {
    // not loaded yet, or the lookup failed: nothing to decide on
    return loading ? null : (
      <div className="mx-auto max-w-xl p-6 text-sm text-muted-foreground" role="status">
        Your access could not be checked. Reload the page.
      </div>
    )
  }

  const allowed =
    need === 'admin' ? isAdmin
      : need === 'moderator' ? moderatesAny
        : moderatesAny || reviewsAny

  if (allowed) return <>{children}</>

  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-3 p-6 text-center" role="alert">
      <ShieldAlert className="h-8 w-8 text-muted-foreground" aria-hidden />
      <h1 className="text-lg font-semibold">No access to this page</h1>
      <p className="text-sm text-muted-foreground">{ADMIN_NOTICE[need]} Ask an administrator of your dataset if you need it.</p>
      <div className="flex gap-2">
        <Button asChild variant="outline" size="sm"><Link href="/my-work">My work</Link></Button>
        <Button asChild variant="outline" size="sm"><Link href="/components">Browse</Link></Button>
      </div>
    </div>
  )
}
