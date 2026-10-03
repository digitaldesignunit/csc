'use client'

/**
 * The folded properties of a component (spec 4.4): per quantity the range
 * the evidence supports, how many records stand behind it, the source tier
 * that won and the confidence; inherited values name their parents. The
 * records a stronger source outranked are listed on demand ("an archival
 * claim outranked by a core test"), which is not the same as corrected.
 */
import { useState } from 'react'
import Link from 'next/link'
import { ChevronDown, ChevronRight, Info } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { EvidenceView, PropertiesView } from '@/generated'
import { EVIDENCE_METHOD_LABELS, vocabLabel } from '@/generated/Vocab'
import {
  formatConfidence,
  formatRange,
  formatResult,
  quantityLabel,
  tierLabel,
  type FoldedProperty,
} from '@/lib/evidence/format'
import { loadProperties } from '@/lib/evidence/api'
import { formatDateAtPrecision } from '@/components/components/componentDetailShared'

function PropertyRow({
  quantity,
  property,
  identityId,
  outranked,
  records,
  loadOutranked,
}: {
  quantity: string
  property: FoldedProperty
  identityId: string
  outranked: string[] | null
  records: Map<string, EvidenceView>
  loadOutranked: () => void
}) {
  const [open, setOpen] = useState(false)
  const inherited = property.source === 'inherited'
  return (
    <li className="space-y-1 rounded-md border border-border p-2.5 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="font-medium">{quantityLabel(quantity)}</span>
        <span className="font-semibold tabular-nums">{formatRange(property.range, property.unit)}</span>
      </div>
      <p className="text-xs text-muted-foreground">
        {tierLabel(property.source)}
        {!inherited && typeof property.n === 'number' ? `, ${property.n} record${property.n === 1 ? '' : 's'}` : ''}
        {property.confidence != null ? `, confidence ${formatConfidence(property.confidence)}` : ''}
      </p>
      {inherited && property.inherited_from && property.inherited_from.length > 0 && (
        <p className="text-xs text-muted-foreground">
          From{' '}
          {property.inherited_from.map((id, i) => (
            <span key={id}>
              {i > 0 ? ', ' : ''}
              <Link href={`/components/${id}`} className="font-mono underline underline-offset-2">{id.slice(0, 8)}</Link>
            </span>
          ))}
          {' '}(weaker than a direct measurement).
        </p>
      )}
      {!inherited && property.evidence_ids && property.evidence_ids.length > 0 && (
        <button type="button" className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
          aria-expanded={open}
          onClick={() => { setOpen((v) => !v); loadOutranked() }}>
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
          Outranked evidence
        </button>
      )}
      {open && (
        <div className="space-y-1 text-xs">
          {outranked === null ? (
            <p className="text-muted-foreground">Loading...</p>
          ) : outranked.length === 0 ? (
            <p className="text-muted-foreground">No records of a lower source for this property.</p>
          ) : (
            <>
              <p className="text-muted-foreground">
                Not used: a stronger source stands for {quantityLabel(quantity).toLowerCase()}.
              </p>
              <ul className="space-y-0.5">
                {outranked.map((id) => {
                  const record = records.get(id)
                  return (
                    <li key={id}>
                      {record
                        ? `${vocabLabel(EVIDENCE_METHOD_LABELS, record.method)}, ${tierLabel(record.source_tier)}: ${formatResult(record.summary)} (${formatDateAtPrecision(record.observed_at, record.observed_at_precision)})`
                        : <Link href={`/components/${identityId}`} className="font-mono">{id.slice(0, 8)}</Link>}
                    </li>
                  )
                })}
              </ul>
            </>
          )}
        </div>
      )}
    </li>
  )
}

export default function PropertiesCard({
  identityId,
  properties,
  versionProperties,
  versionLabel,
  records,
}: {
  identityId: string
  /** identity.properties of the passport */
  properties: Record<string, unknown> | null | undefined
  /** properties of the version on screen (snapshot-scoped quantities) */
  versionProperties: Record<string, unknown> | null | undefined
  versionLabel: string
  records: EvidenceView[]
}) {
  const [view, setView] = useState<PropertiesView | null>(null)
  const byId = new Map(records.map((r) => [r._id, r]))
  const request = () => {
    if (view) return
    loadProperties(identityId).then(setView).catch(() => setView({
      identity_id: identityId, properties: {}, outranked_evidence_ids: {},
    }))
  }
  const blocks: { title: string; entries: [string, FoldedProperty][]; outrankedFor: boolean }[] = [
    { title: 'The piece', entries: Object.entries((properties ?? {}) as Record<string, FoldedProperty>), outrankedFor: true },
    { title: versionLabel, entries: Object.entries((versionProperties ?? {}) as Record<string, FoldedProperty>), outrankedFor: false },
  ].filter((block) => block.entries.length > 0)

  return (
    <section aria-label="Properties" className="space-y-3">
      <div className="flex items-center gap-2">
        <Info className="h-4 w-4 text-muted-foreground" />
        <h3 className="text-sm font-semibold">Properties from the evidence</h3>
      </div>
      {blocks.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No published evidence yet: nothing is known about this piece beyond what its record says.
        </p>
      )}
      {blocks.map((block) => (
        <div key={block.title} className="space-y-1.5">
          <div className="flex items-center gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{block.title}</h4>
            {!block.outrankedFor && <Badge variant="outline" className="text-[10px]">this version</Badge>}
          </div>
          <ul className="grid gap-2 sm:grid-cols-2">
            {block.entries.map(([quantity, property]) => (
              <PropertyRow
                key={quantity}
                quantity={quantity}
                property={property}
                identityId={identityId}
                outranked={block.outrankedFor ? (view ? (view.outranked_evidence_ids[quantity] as string[] | undefined) ?? [] : null) : []}
                records={byId}
                loadOutranked={request}
              />
            ))}
          </ul>
        </div>
      ))}
    </section>
  )
}
