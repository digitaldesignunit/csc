'use client'

/**
 * The evidence records of the component (decision 8.118): every record with
 * its status, verification and files, and the lifecycle actions in the card's
 * own menu. No timeline here: the History card has it. Documents of a batch the
 * piece was drawn from are listed on top.
 */
import { useEffect, useRef } from 'react'
import { FlaskConical } from 'lucide-react'

import BatchDocuments from '@/components/evidence/BatchDocuments'
import EvidenceCard from '@/components/evidence/EvidenceCard'
import { Button } from '@/components/ui/button'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { UPLOAD_HELP } from '@/lib/evidence/api'
import { recordIdOfHash } from '@/lib/history/recordTarget'
import { scrollToRecord } from '@/lib/history/scrollToRecord'
import { useRegistry } from '@/lib/evidence/useRegistry'
import AddEvidenceButton from './AddEvidenceButton'
import { useEvidenceData } from './EvidenceData'

export default function ComponentRecordsCard({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const { registry } = useRegistry()
  const { records, error, changed, showCorrected, setShowCorrected } = useEvidenceData()
  const scrolledFor = useRef<string | null>(null)

  // an address `#record-<id>` (a click in the History graph of another piece): once the records
  // have loaded, open "Show corrected records" when the record is one of them, and scroll to it
  useEffect(() => {
    if (records === null) return
    const id = recordIdOfHash(window.location.hash)
    if (!id || scrolledFor.current === id) return
    scrolledFor.current = id
    if (records.some((r) => String(r._id) === id && r.superseded_by)) setShowCorrected(true)
    void scrollToRecord(id, { smooth: false })
  }, [records, setShowCorrected])

  const live = (records ?? []).filter((r) => !r.superseded_by && 'method' in r)
  const corrected = (records ?? []).filter((r) => r.superseded_by && 'method' in r)
  const waiting = live.filter((r) => r.status !== 'published')
  const published = live.filter((r) => r.status === 'published')
  const newestFirst = (a: (typeof live)[number], b: (typeof live)[number]) => b.observed_at.localeCompare(a.observed_at)
  const help = registry?.help(...UPLOAD_HELP)
  // the cards of this page: a paired record is linked only when it is one of them
  const shownIds = [...live, ...(showCorrected ? corrected : [])].map((record) => String(record._id))
  const card = (record: (typeof live)[number]) => (
    <EvidenceCard key={record._id} record={record} dataset={identity.dataset} onChanged={changed}
      uploadHelp={help} menu shownIds={shownIds} />
  )

  return (
    <section aria-label="Evidence records" className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical className="h-4 w-4" />
          Evidence records{records ? ` (${live.length})` : ''}
        </h2>
        <AddEvidenceButton
          identityId={String(identity._id ?? '')}
          dataset={identity.dataset}
          withdrawn={identity.withdrawn}
          currentSnapshotId={identity.current_snapshot_id}
        />
      </div>
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
              onClick={() => setShowCorrected(!showCorrected)}>
              {showCorrected ? 'Hide' : 'Show'} corrected records ({corrected.length})
            </Button>
            {showCorrected && [...corrected].sort(newestFirst).map((record) => (
              <EvidenceCard key={record._id} record={record} dataset={identity.dataset} onChanged={changed} menu
                shownIds={shownIds} />
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
