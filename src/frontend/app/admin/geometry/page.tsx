'use client'

/**
 * Snapshots whose geometry stages failed (decision 8.60), for admin: the
 * stage and the stored text of each failure, and a retry. The retry is the
 * moderator's recompute (`POST /snapshots/{id}/proxies/recompute`): it
 * recomputes frame and class at once and the heavy stages here or, with a
 * remote worker, marks them for it.
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { RefreshCw, TriangleAlert } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'

type FailedSnapshot = {
  snapshot_id: string
  identity_id: string
  catalog_number?: number | null
  dataset?: string | null
  version?: number | null
  status?: string | null
  stages: Record<string, string>
}

export default function GeometryFailuresPage() {
  const router = useRouter()
  const { me, loading: meLoading, isAdmin } = useMe()
  const [rows, setRows] = useState<FailedSnapshot[]>([])
  const [loading, setLoading] = useState(true)
  const [retrying, setRetrying] = useState<string | null>(null)

  useEffect(() => {
    if (!meLoading && me && !isAdmin) router.push('/')
  }, [me, meLoading, isAdmin, router])

  const load = useCallback(async () => {
    try {
      setRows(await backendJson<FailedSnapshot[]>('/geometry/failed'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not load the list')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isAdmin) void load()
  }, [isAdmin, load])

  const retry = async (row: FailedSnapshot) => {
    setRetrying(row.snapshot_id)
    try {
      await backendJson(`/snapshots/${encodeURIComponent(row.snapshot_id)}/proxies/recompute`, {
        method: 'POST',
      })
      toast.success('Recomputed')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Recompute failed')
    } finally {
      setRetrying(null)
    }
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <TriangleAlert className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold sm:text-2xl">Geometry failures</h1>
        </div>
        <Button size="sm" variant="outline" onClick={() => void load()}>
          <RefreshCw className="mr-1 h-4 w-4" />Refresh
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Snapshots with a failed geometry stage. A failed stage keeps the last good values and is
        not retried by the cron until its input changes; Retry runs it again.
      </p>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No failed stages.</p>
      ) : (
        <div className="space-y-2">
          {rows.map((row) => (
            <Card key={row.snapshot_id}>
              <CardContent className="flex flex-wrap items-start justify-between gap-3 p-4">
                <div className="min-w-0 space-y-1 text-sm">
                  <Link
                    href={`/components/${encodeURIComponent(row.identity_id)}?snapshots=${encodeURIComponent(row.snapshot_id)}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    #{row.catalog_number ?? '?'} v{row.version ?? '?'}
                  </Link>
                  <span className="ml-2 text-muted-foreground">
                    {row.dataset ?? ''} {row.status ?? ''}
                  </span>
                  {Object.entries(row.stages).map(([stage, message]) => (
                    <p key={stage} className="break-words text-xs text-muted-foreground">
                      <span className="font-medium text-foreground">{stage}</span>: {message}
                    </p>
                  ))}
                </div>
                <Button
                  size="sm"
                  disabled={retrying === row.snapshot_id}
                  onClick={() => void retry(row)}
                >
                  Retry
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
