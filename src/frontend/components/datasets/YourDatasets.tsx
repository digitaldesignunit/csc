'use client'

/**
 * "Your datasets" in My work (decision 8.139 j): the datasets you hold a role
 * in, whether they wait for an administrator's review, and "New dataset" for
 * anyone with a verified e-mail address (a user without a role sees no
 * Moderation group, so this is where they start). The limit per account is
 * the API's: its message appears in the dialog when it is reached.
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Database } from 'lucide-react'

import NewDatasetDialog from '@/components/datasets/NewDatasetDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { DatasetView } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { browseUrl } from '@/lib/browse'
import { awaitsReview, datasetCounts } from '@/lib/datasets'
import { useMe } from '@/lib/me'

/** The grey line of a row: slug, counts and, for a member, the roles. */
function subtitle(dataset: DatasetView, isAdmin: boolean): string {
  const counts = datasetCounts(dataset)
  return `${dataset._id}${counts ? `, ${counts}` : ''}${isAdmin ? '' : `, ${(dataset.roles ?? []).join(', ')}`}`
}

export default function YourDatasets() {
  const router = useRouter()
  const { me, isAdmin, moderates } = useMe()
  const [rows, setRows] = useState<DatasetView[] | null>(null)

  const load = useCallback(async () => {
    try {
      const all = await backendJson<DatasetView[]>('/datasets')
      setRows(all.filter((d) => isAdmin || (d.roles ?? []).length > 0))
    } catch {
      setRows([])
    }
  }, [isAdmin])

  useEffect(() => {
    if (me) void load()
  }, [me, load])

  if (!me) return null
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3 pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Database className="h-4 w-4 text-primary" aria-hidden />
          Your datasets{rows ? ` (${rows.length})` : ''}
        </CardTitle>
        <NewDatasetDialog variant="outline"
          onCreated={(slug) => router.push(`/admin/datasets/${encodeURIComponent(slug)}`)} />
      </CardHeader>
      <CardContent className="text-sm">
        {rows === null ? (
          <p className="text-muted-foreground">Loading...</p>
        ) : rows.length === 0 ? (
          <p className="text-muted-foreground">
            You are not a member of a dataset yet. Start one for your own elements, or ask a moderator to add you
            to theirs.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {rows.map((dataset) => (
              <li key={dataset._id} className="flex flex-col gap-2 py-2 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-x-1.5 font-medium">
                    <span className="min-w-0 break-words" title={dataset.name}>{dataset.name}</span>
                    {awaitsReview(dataset) && (
                      <Badge variant="outline" className="shrink-0 border-amber-400 text-[10px] text-amber-800 dark:text-amber-200">
                        Awaiting review
                      </Badge>
                    )}
                  </p>
                  <p className="break-words text-xs text-muted-foreground" title={subtitle(dataset, isAdmin)}>
                    {subtitle(dataset, isAdmin)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {(isAdmin || moderates(dataset._id)) && (
                    <Button asChild variant="outline" size="sm" className="h-8 text-xs">
                      <Link href={`/admin/datasets/${encodeURIComponent(dataset._id)}`}>Manage</Link>
                    </Button>
                  )}
                  <Button asChild variant="ghost" size="sm" className="h-8 text-xs">
                    <Link href={browseUrl('dataset', dataset._id)}>Browse</Link>
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
