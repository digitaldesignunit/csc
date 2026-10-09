'use client'

/**
 * The correction warning (spec 3.3.2, decisions 8.16 d, 8.87 c): when a
 * correction changes the geometry, the published evidence positioned on the
 * previous version keeps its points, which no longer mean what they did. Each
 * record links to its own correction in the evidence form, where the point is
 * picked again; there is no bulk re-placing tool in 0.6.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { MapPin, TriangleAlert } from 'lucide-react'

import type { EvidenceView } from '@/generated'
import { EVIDENCE_METHOD_LABELS, vocabLabel } from '@/generated/Vocab'
import { formatResult } from '@/lib/evidence/format'
import { loadEvidenceOf } from '@/lib/evidence/api'
import { formatDateAtPrecision } from '@/components/components/componentDetailShared'

/** Published, uncorrected records whose point was picked on this snapshot. */
export function positionedOn(records: EvidenceView[], snapshotId: string): EvidenceView[] {
  return records.filter((r) =>
    r.status === 'published' && !r.superseded_by && r.position?.snapshot_id === snapshotId)
}

export function usePositionedEvidence(identityId: string, snapshotId: string, enabled: boolean) {
  const [state, setState] = useState<{ key: string; records: EvidenceView[] } | null>(null)
  const key = `${identityId}:${snapshotId}`
  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    loadEvidenceOf(identityId, 'status=published')
      .then((rows) => { if (!cancelled) setState({ key, records: positionedOn(rows, snapshotId) }) })
      .catch(() => { if (!cancelled) setState({ key, records: [] }) })
    return () => { cancelled = true }
  }, [identityId, snapshotId, enabled, key])
  return enabled && state?.key === key ? state.records : null
}

export function PositionedEvidence({
  identityId,
  records,
  newTab,
}: {
  identityId: string
  records: EvidenceView[]
  /** Open the corrections in a new tab (the form is not finished yet). */
  newTab?: boolean
}) {
  if (records.length === 0) return null
  return (
    <section
      role="status"
      className="space-y-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
    >
      <p className="flex items-start gap-2 font-medium">
        <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
        {records.length === 1
          ? '1 evidence record is positioned on the previous version.'
          : `${records.length} evidence records are positioned on the previous version.`}
      </p>
      <p className="text-xs opacity-90">
        They keep their points, and the viewer draws them only on that version. Correct each one in the
        evidence form to pick its point again on the new geometry.
      </p>
      <ul className="space-y-1.5">
        {records.map((record) => (
          <li key={record._id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-amber-300/70 bg-background/60 px-2 py-1.5">
            <span className="min-w-0 text-xs">
              <MapPin className="mr-1 inline h-3 w-3" />
              {vocabLabel(EVIDENCE_METHOD_LABELS, record.method)}: {formatResult(record.summary)}
              {' '}({formatDateAtPrecision(record.observed_at, record.observed_at_precision)})
              {record.position?.description ? `, ${record.position.description}` : ''}
            </span>
            <Link
              href={`/components/${encodeURIComponent(identityId)}/evidence/new?correct=${encodeURIComponent(record._id)}`}
              className="shrink-0 text-xs font-medium underline underline-offset-4"
              {...(newTab ? { target: '_blank', rel: 'noopener' } : {})}
            >
              Correct this record
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
