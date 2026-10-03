'use client'

/**
 * The evidence part of the component page (plan P6): the folded properties,
 * the records (with the lifecycle and verification the caller may use) and
 * the timeline. "Add evidence" opens the one evidence form (decision 7.1).
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { FlaskConical, Plus } from 'lucide-react'

import EvidenceCard from '@/components/evidence/EvidenceCard'
import PropertiesCard from '@/components/evidence/PropertiesCard'
import TimelineView from '@/components/evidence/TimelineView'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import type { EvidenceView } from '@/generated'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { BackendError } from '@/lib/backend'
import { UPLOAD_HELP, loadEvidenceOf } from '@/lib/evidence/api'
import { useRegistry } from '@/lib/evidence/useRegistry'
import { useMe } from '@/lib/me'

export default function ComponentEvidenceSection({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const identityId = String(identity._id ?? '')
  const snapshot = primarySnapshot(catalog)
  const { me, rolesIn } = useMe()
  const { registry } = useRegistry()
  const [records, setRecords] = useState<EvidenceView[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showCorrected, setShowCorrected] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  const canRecord = !!me && rolesIn(identity.dataset).includes('contributor')
    && !identity.withdrawn && !!identity.current_snapshot_id

  const load = useCallback(() => {
    loadEvidenceOf(identityId)
      .then((rows) => { setRecords(rows); setError(null) })
      .catch((err) => {
        setRecords([])
        setError(err instanceof BackendError ? err.message : 'Could not load the evidence.')
      })
  }, [identityId])

  useEffect(() => { load() }, [load, me?._id])

  const changed = () => {
    load()
    setReloadKey((k) => k + 1)
  }

  const live = (records ?? []).filter((r) => !r.superseded_by && 'method' in r)
  const corrected = (records ?? []).filter((r) => r.superseded_by && 'method' in r)
  const waiting = live.filter((r) => r.status !== 'published')
  const published = live.filter((r) => r.status === 'published')
  const newestFirst = (a: EvidenceView, b: EvidenceView) => b.observed_at.localeCompare(a.observed_at)
  const version = typeof snapshot.version === 'number' ? `This version (v${snapshot.version})` : 'This version'

  return (
    <Card className="shadow-sm">
      <CardContent className="space-y-4 pt-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">Evidence</h2>
          </div>
          {canRecord && (
            <Button asChild size="sm">
              <Link href={`/components/${encodeURIComponent(identityId)}/evidence/new`}>
                <Plus className="mr-1 h-4 w-4" />Add evidence
              </Link>
            </Button>
          )}
        </div>

        <PropertiesCard
          identityId={identityId}
          properties={identity.properties}
          versionProperties={snapshot.properties}
          versionLabel={version}
          records={records ?? []}
        />

        <Tabs defaultValue="records">
          <TabsList>
            <TabsTrigger value="records">Records{records ? ` (${live.length})` : ''}</TabsTrigger>
            <TabsTrigger value="timeline">Evidence timeline</TabsTrigger>
          </TabsList>
          <TabsContent value="records" className="space-y-3 pt-2">
            {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
            {records === null && <p className="text-sm text-muted-foreground">Loading...</p>}
            {records !== null && live.length === 0 && !error && (
              <p className="text-sm text-muted-foreground">No evidence recorded for this piece yet.</p>
            )}
            {waiting.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Not published yet</h3>
                {waiting.sort(newestFirst).map((record) => (
                  <EvidenceCard key={record._id} record={record} dataset={identity.dataset} onChanged={changed}
                    uploadHelp={registry?.help(...UPLOAD_HELP)} />
                ))}
              </div>
            )}
            {published.length > 0 && (
              <div className="space-y-2">
                {waiting.length > 0 && (
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Published</h3>
                )}
                {published.sort(newestFirst).map((record) => (
                  <EvidenceCard key={record._id} record={record} dataset={identity.dataset} onChanged={changed}
                    uploadHelp={registry?.help(...UPLOAD_HELP)} />
                ))}
              </div>
            )}
            {corrected.length > 0 && (
              <div className="space-y-2">
                <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" aria-expanded={showCorrected}
                  onClick={() => setShowCorrected((v) => !v)}>
                  {showCorrected ? 'Hide' : 'Show'} corrected records ({corrected.length})
                </Button>
                {showCorrected && corrected.sort(newestFirst).map((record) => (
                  <EvidenceCard key={record._id} record={record} dataset={identity.dataset} onChanged={changed} />
                ))}
              </div>
            )}
          </TabsContent>
          <TabsContent value="timeline" className="pt-3">
            <TimelineView identityId={identityId} reloadKey={reloadKey} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
