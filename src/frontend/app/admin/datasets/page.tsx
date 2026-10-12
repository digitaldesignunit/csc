'use client'

/**
 * Datasets (spec section 3.6, section 7.7, decision 8.139): admin sees all;
 * a moderator sees the datasets they moderate and manages them. Anyone who
 * moderates can start a new dataset; it waits for an administrator's review.
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Database } from 'lucide-react'

import NewDatasetDialog from '@/components/datasets/NewDatasetDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import type { DatasetView } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { browseUrl } from '@/lib/browse'
import { awaitsReview, datasetCounts } from '@/lib/datasets'
import { useMe } from '@/lib/me'

export default function DatasetsPage() {
  const router = useRouter()
  const { me, loading: meLoading, isAdmin, moderates, moderatesAny } = useMe()
  const [datasets, setDatasets] = useState<DatasetView[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!meLoading && me && !moderatesAny) router.push('/')
  }, [me, meLoading, moderatesAny, router])

  const load = useCallback(async () => {
    try {
      const all = await backendJson<DatasetView[]>('/datasets')
      setDatasets(all.filter((d) => moderates(d._id)))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not load datasets')
    } finally {
      setLoading(false)
    }
  }, [moderates])

  useEffect(() => {
    if (moderatesAny) void load()
  }, [moderatesAny, load])

  return (
    <div className="container mx-auto max-w-4xl space-y-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold sm:text-2xl">Datasets</h1>
        </div>
        <NewDatasetDialog onCreated={(slug) => router.push(`/admin/datasets/${encodeURIComponent(slug)}`)} />
      </div>
      <p className="text-sm text-muted-foreground">
        A dataset is a project: its members, their roles and who sees its components.
        {isAdmin ? ' You see all datasets as admin.' : ' You see the datasets you moderate.'}
      </p>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <ul className="space-y-2">
          {datasets.map((dataset) => (
            <li key={dataset._id}>
              <Card>
                <CardContent className="flex flex-col gap-2 p-3 text-sm lg:flex-row lg:items-center">
                  <div className="min-w-0 lg:flex-1">
                    <div className="truncate font-medium" title={dataset.name}>{dataset.name}</div>
                    <div
                      className="truncate text-xs text-muted-foreground"
                      title={`${dataset._id}${datasetCounts(dataset) ? `, ${datasetCounts(dataset)}` : ''}`}
                    >
                      {dataset._id}
                      {datasetCounts(dataset) && <>, {datasetCounts(dataset)}</>}
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 lg:shrink-0">
                    {awaitsReview(dataset) && (
                      <Badge variant="outline" className="border-amber-400 text-amber-800 dark:text-amber-200">
                        Awaiting review
                      </Badge>
                    )}
                    <Badge variant={dataset.visibility === 'catalog' ? 'secondary' : 'outline'}>
                      {dataset.visibility === 'catalog' ? 'Visible to signed-in users' : 'Members only'}
                    </Badge>
                  </div>
                  <div className="flex gap-2 lg:shrink-0">
                    {(isAdmin || moderates(dataset._id)) && (
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/admin/datasets/${encodeURIComponent(dataset._id)}`}>Edit</Link>
                      </Button>
                    )}
                    <Button asChild variant="outline" size="sm">
                      <Link href={browseUrl('dataset', dataset._id)}>Browse components</Link>
                    </Button>
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
