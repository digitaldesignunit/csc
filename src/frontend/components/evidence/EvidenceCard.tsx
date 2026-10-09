'use client'

/**
 * One evidence record as a card: what it says (the headline result and
 * derived results), what the server computed and warned about, where on
 * the piece, who performed it, its files, its moderation status and its
 * verification. Used in the component page's list, in the form's review
 * step and in the queues.
 */
import { useState } from 'react'
import Link from 'next/link'
import { ChevronDown, ChevronRight, MapPin, TriangleAlert } from 'lucide-react'

import EvidenceAttachments from '@/components/evidence/EvidenceAttachments'
import EvidenceLifecycleActions from '@/components/moderation/EvidenceLifecycleActions'
import VerificationPanel from '@/components/moderation/VerificationPanel'
import { Badge } from '@/components/ui/badge'
import type { Actor, EvidenceView } from '@/generated'
import { EVIDENCE_METHOD_LABELS, STATUS_LABELS, VERIFICATION_STATE_LABELS, vocabLabel } from '@/generated/Vocab'
import { formatResult, quantityLabel, statusClass, tierLabel, verificationClass } from '@/lib/evidence/format'
import { serverFacts } from '@/lib/evidence/facts'
import { roundVec, type Vec3 } from '@/lib/evidence/grid'
import { useRegistry } from '@/lib/evidence/useRegistry'
import { formatDateAtPrecision } from '@/components/components/componentDetailShared'
import { documentOf } from '@/lib/evidence/document'

function who(actor: Actor): string {
  return [actor.name, actor.organization].filter(Boolean).join(', ') || 'someone'
}

export default function EvidenceCard({
  record,
  dataset,
  onChanged,
  defaultOpen = false,
  uploadHelp,
  menu = false,
}: {
  record: EvidenceView
  dataset: string | null | undefined
  onChanged: () => void
  defaultOpen?: boolean
  uploadHelp?: string
  /** The lifecycle actions in a menu of the card's own (the component page, 8.118). */
  menu?: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const { registry } = useRegistry()
  const method = registry?.methods.find((m) => m.name === record.method)
  const facts = serverFacts(method, record.payload)
  const payload = (record.payload ?? {}) as Record<string, { label?: string | null } | undefined>
  const label = payload.test_area?.label || payload.specimen?.label || null
  const state = record.verification?.state ?? 'unverified'
  const warnings = record.warnings ?? []
  const point = record.position?.point as Vec3 | null | undefined
  const attachments = (record.attachments ?? []).filter((a) => !a.removed).length
  const cited = documentOf(record.payload)
  // no result: the record documents the piece and never enters the fold (8.106)
  const isDocument = !record.summary

  return (
    <article className="relative rounded-lg border border-border bg-card text-sm" aria-label={`Evidence ${vocabLabel(EVIDENCE_METHOD_LABELS, record.method)}`}>
      {menu && (
        <div className="absolute right-1.5 top-1.5 z-10">
          <EvidenceLifecycleActions record={record} dataset={dataset} onChanged={onChanged} variant="menu" />
        </div>
      )}
      <button
        type="button"
        className={`flex w-full items-start gap-2 p-3 text-left${menu ? ' pr-10' : ''}`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? <ChevronDown className="mt-0.5 h-4 w-4 shrink-0" /> : <ChevronRight className="mt-0.5 h-4 w-4 shrink-0" />}
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium">{isDocument ? 'Document' : vocabLabel(EVIDENCE_METHOD_LABELS, record.method)}</span>
            {label && <span className="text-muted-foreground">{label}</span>}
            <Badge variant="outline" className={`text-[10px] ${statusClass(record.status)}`}>
              {vocabLabel(STATUS_LABELS, record.status)}
            </Badge>
            <Badge variant="outline" className={`text-[10px] ${verificationClass(state)}`}>
              {vocabLabel(VERIFICATION_STATE_LABELS, state)}
            </Badge>
            {record.superseded_by && <Badge variant="outline" className="text-[10px]">Corrected</Badge>}
            {record.supersedes && <Badge variant="outline" className="text-[10px]">Correction</Badge>}
            {warnings.length > 0 && (
              <Badge variant="outline" className="border-amber-400 text-[10px] text-amber-800 dark:text-amber-200">
                <TriangleAlert className="mr-1 h-3 w-3" />{warnings.length}
              </Badge>
            )}
          </div>
          {record.summary ? (
            <p>
              <span className="text-muted-foreground">{quantityLabel(record.summary.quantity)}: </span>
              <span className="font-medium tabular-nums">{formatResult(record.summary)}</span>
            </p>
          ) : (
            <p className="font-medium">{cited?.title ?? 'Untitled document'}</p>
          )}
          <p className="text-xs text-muted-foreground">
            {formatDateAtPrecision(record.observed_at, record.observed_at_precision)}
            {attachments > 0 ? `, ${attachments} file${attachments === 1 ? '' : 's'}` : ''}
          </p>
        </div>
      </button>

      {open && (
        <div className="space-y-3 border-t border-border p-3">
          {(record.derived ?? []).map((d, i) => (
            <p key={i} className="text-xs">
              <span className="text-muted-foreground">{quantityLabel(d.quantity)} ({d.model.kind}): </span>
              <span className="font-medium">{formatResult(d)}</span>
              {d.model.note ? ` - ${d.model.note}` : ''}
              {d.model.reference ? ` (${d.model.reference})` : ''}
            </p>
          ))}

          {cited?.href && (
            <p className="text-xs">
              <span className="text-muted-foreground">Source: </span>
              <a href={cited.href} target="_blank" rel="noopener noreferrer"
                className="font-medium underline underline-offset-2">
                {cited.host}
              </a>
              {cited.retrievedAt ? (
                <span className="text-muted-foreground"> (read {formatDateAtPrecision(cited.retrievedAt, cited.retrievedAt.length === 4 ? 'year' : cited.retrievedAt.length === 7 ? 'month' : 'day')})</span>
              ) : null}
            </p>
          )}

          {facts.length > 0 && (
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs" aria-label="Computed by the server">
              {facts.map((f) => (
                <div key={f.path} className="contents">
                  <dt className="text-muted-foreground" title={f.help}>{f.label}</dt>
                  <dd className="tabular-nums">{f.value}</dd>
                </div>
              ))}
            </dl>
          )}

          {warnings.length > 0 && (
            <ul className="space-y-1 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100" role="status">
              {warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}

          <div className="flex flex-wrap items-start gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {record.position?.description || (record.position?.kind === 'none' ? 'whole piece' : record.position?.kind)}
              {point ? ` (${roundVec(point, 1).join(', ')} mm)` : ''}
            </span>
            <span>{tierLabel(record.source_tier)}</span>
            {record.standard && <span>{record.standard.code}{record.standard.year ? ` (${record.standard.year})` : ''}</span>}
            {record.sampled_at && <span>sampled {formatDateAtPrecision(record.sampled_at, record.sampled_at_precision)}</span>}
          </div>
          {(record.performed_by ?? []).length > 0 && (
            <p className="text-xs text-muted-foreground">
              Performed by {(record.performed_by ?? []).map((a) => who(a)).join('; ')}
              {record.recorded_by_username ? `. Recorded by ${record.recorded_by_username}` : ''}
            </p>
          )}
          {record.notes && <p className="whitespace-pre-line text-xs">{record.notes}</p>}
          {record.supersedes && (
            <p className="text-xs text-muted-foreground">
              Corrects{' '}
              <Link href={`/components/${record.identity_id}`} className="font-mono underline underline-offset-2">
                {record.supersedes.slice(0, 8)}
              </Link>
            </p>
          )}

          <VerificationPanel record={record} dataset={dataset} onChanged={onChanged} />
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Files</p>
            <EvidenceAttachments record={record} dataset={dataset} onChanged={onChanged} uploadHelp={uploadHelp} />
          </div>
          {!menu && <EvidenceLifecycleActions record={record} dataset={dataset} onChanged={onChanged} />}
        </div>
      )}
    </article>
  )
}
