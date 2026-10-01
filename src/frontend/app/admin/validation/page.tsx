'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ExternalLink, Shield } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { PendingSnapshotItem } from '@/generated/SnapshotModels'
import { ORIGINAL_FUNCTION_LABELS, vocabLabel } from '@/generated/Vocab'
import { formatTimestamp } from '@/lib/utils'

function pendingSnapshotHref(row: PendingSnapshotItem): string {
  const params = new URLSearchParams({ snapshots: row._id })
  return `/components/${encodeURIComponent(row.identity_id)}?${params.toString()}`
}

/**
 * Moderation queue, read-only during the 0.6 migration: snapshots with
 * status pending. Publish / reject return with the per-dataset queues of
 * plan P3.
 */
export default function ModerationQueuePage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [pending, setPending] = useState<PendingSnapshotItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
      router.push('/')
    }
  }, [session, status, router])

  useEffect(() => {
    if (session?.user?.role !== 'admin' || session.error) return
    const load = async () => {
      try {
        const response = await fetch('/api/backend/snapshots/pending', {
          credentials: 'include',
        })
        if (response.ok) {
          setPending((await response.json()) as PendingSnapshotItem[])
        }
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [session])

  return (
    <div className="container mx-auto max-w-4xl space-y-4 p-6">
      <div className="flex items-center gap-2">
        <Shield className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold sm:text-2xl">Moderation queue</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Snapshots waiting to be published. Publishing and rejecting return with the 0.6
        moderation workflow; until then this list is read-only.
      </p>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : pending.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Nothing is waiting for moderation.
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-2">
          {pending.map((row) => (
            <li key={row._id}>
              <Card>
                <CardContent className="flex flex-wrap items-center justify-between gap-2 p-3 text-sm">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="font-medium">{row.name || row.identity_id}</span>
                    <Badge variant="outline">v{row.version}</Badge>
                    {row.catalog_number != null && (
                      <Badge variant="secondary">#{row.catalog_number}</Badge>
                    )}
                    <span className="text-muted-foreground">
                      {[vocabLabel(ORIGINAL_FUNCTION_LABELS, row.original_function),
                        row.material, row.dataset]
                        .filter(Boolean)
                        .join(' / ')}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    <span>{formatTimestamp(row.created)}</span>
                    <Link
                      href={pendingSnapshotHref(row)}
                      className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                    >
                      Open <ExternalLink className="h-3 w-3" />
                    </Link>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
