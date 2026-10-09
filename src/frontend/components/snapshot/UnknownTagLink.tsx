'use client'

/**
 * Where the scanners lead for a tag no component has (spec 7.5, decision
 * 8.87): a line with a link to `/id/{uuid}`, which offers a contributor
 * *New component* and *Cut from pieces*. Nothing is shown for a known tag,
 * for a caller who contributes nowhere, or while the lookup is open.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { PackagePlus } from 'lucide-react'

import { useMe } from '@/lib/me'
import { uuidFromScan } from '@/lib/scanIds'

export default function UnknownTagLink({ id, className }: { id: string | null | undefined; className?: string }) {
  const { me, isAdmin } = useMe()
  const tag = uuidFromScan(id)
  const [unknown, setUnknown] = useState<string | null>(null)
  const contributes = isAdmin || (me?.memberships ?? []).some((m) => m.roles.includes('contributor'))

  useEffect(() => {
    if (!tag || !contributes) return
    let cancelled = false
    fetch(`/api/backend/identities/${encodeURIComponent(tag)}?expand=none`, { credentials: 'include', cache: 'no-store' })
      .then((res) => { if (!cancelled) setUnknown(res.status === 404 ? tag : null) })
      .catch(() => { if (!cancelled) setUnknown(null) })
    return () => { cancelled = true }
  }, [tag, contributes])

  if (!tag || !contributes || unknown !== tag) return null
  return (
    <p className={className ?? 'text-xs text-muted-foreground'}>
      This tag is not in the catalog yet.{' '}
      <Link href={`/id/${tag}`} className="inline-flex items-center gap-1 font-medium text-primary underline underline-offset-4">
        <PackagePlus className="h-3 w-3" />
        Record it
      </Link>
    </p>
  )
}
