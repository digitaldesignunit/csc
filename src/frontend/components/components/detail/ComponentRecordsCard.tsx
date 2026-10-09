'use client'

/**
 * The evidence records of the component (decision 8.118): every record with
 * its status, verification and files, and the lifecycle actions in the card's
 * own menu. No timeline here: the History card has it. Documents of a batch the
 * piece was drawn from are listed on top.
 */
import { useState } from 'react'
import { FlaskConical } from 'lucide-react'

import BatchDocuments from '@/components/evidence/BatchDocuments'
import EvidenceCard from '@/components/evidence/EvidenceCard'
import { Button } from '@/components/ui/button'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { UPLOAD_HELP } from '@/lib/evidence/api'
import { useRegistry } from '@/lib/evidence/useRegistry'
import { useEvidenceData } from './EvidenceData'

export default function ComponentRecordsCard({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const { registry } = useRegistry()
  const { records, error, changed } = useEvidenceData()
  const [showCorrected, setShowCorrected] = useState(false)

  const live = (records ?? []).filter((r) => !r.superseded_by && 'method' in r)
  const corrected = (records ?? []).filter((r) => r.superseded_by && 'method' in r)
  const waiting = live.filter((r) => r.status !== 'published')
  const published = live.filter((r) => r.status === 'published')
  const newestFirst = (a: (typeof live)[number], b: (typeof live)[number]) => b.observed_at.localeCompare(a.observed_at)
  const help = registry?.help(...UPLOAD_HELP)
  const card = (record: (typeof live)[number]) => (
    <EvidenceCard key={record._id} record={record} dataset={identity.dataset} onChanged={changed}
      uploadHelp={help} menu />
  )

  return (
    <section aria-label="Evidence records" className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <FlaskConical className="h-4 w-4" />
        Evidence records{records ? ` (${live.length})` : ''}
      </h2>
      <div className="space-y-3">
        <BatchDocuments identity={identity} />
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        {records === null && <p className="text-sm text-muted-foreground">Loading...</p>}
        {records !== null && live.length === 0 && !error && (
          <p className="text-sm text-muted-foreground">No evidence recorded yet.</p>
        )}
        {waiting.length > 0 && (
          <div className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Not published yet</h3>
            {[...waiting].sort(newestFirst).map(card)}
          </div>
        )}
        {published.length > 0 && (
          <div className="space-y-2">
            {waiting.length > 0 && (
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Published</h3>
            )}
            {[...published].sort(newestFirst).map(card)}
          </div>
        )}
        {corrected.length > 0 && (
          <div className="space-y-2">
            <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" aria-expanded={showCorrected}
              onClick={() => setShowCorrected((v) => !v)}>
              {showCorrected ? 'Hide' : 'Show'} corrected records ({corrected.length})
            </Button>
            {showCorrected && [...corrected].sort(newestFirst).map((record) => (
              <EvidenceCard key={record._id} record={record} dataset={identity.dataset} onChanged={changed} menu />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
