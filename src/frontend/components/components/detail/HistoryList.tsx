'use client'

/**
 * The List rendering of the History card (decision 8.102): what happened to
 * the component, in time order --- archived cycles, the origin, the
 * deinstallation, every state and correction, every evidence record, the exit
 * (spec 4.1, 8.68) --- with the lineage events (cut from, cut into, assembled
 * from) in their place. The layers decide what is listed; the origin, the
 * deinstallation and the exit are always there.
 */
import Link from 'next/link'
import { Archive, Camera, FlaskConical, GitBranch, LogOut, Package, Sparkles, Wrench } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  EVIDENCE_METHOD_LABELS,
  EXIT_KIND_LABELS,
  ORIGIN_KIND_LABELS,
  VERIFICATION_STATE_LABELS,
  vocabLabel,
} from '@/generated/Vocab'
import { formatResult, quantityLabel } from '@/lib/evidence/format'
import { formatDay, mergeHistory, type HistoryEvent, type Layers, type LineageEvent } from '@/lib/componentDetail'

export type TimelineEvent = HistoryEvent & {
  planned?: boolean
  cycle?: number | null
  detail?: string | null
  record_id?: string
  version?: number
  status?: string
  name?: string | null
  corrected?: boolean
  corrects?: string | null
  withdrawn?: boolean
  method?: string
  quantity?: string
  value?: number | string | null
  range?: (number | string)[] | null
  unit?: string | null
  verification?: string | null
  resolution?: string | null
  paths?: string[]
}

const SECTIONS: Record<string, string> = {
  before_cataloguing: 'Before the piece was catalogued',
  history: 'In the catalog',
  after_leaving_circulation: 'After the piece left circulation',
}

function Related({ event }: { event: LineageEvent }) {
  return (
    <>
      {event.related.map((r, i) => (
        <span key={r.id}>
          {i > 0 ? ', ' : ''}
          <Link href={`/components/${encodeURIComponent(r.id)}`} className="font-medium underline underline-offset-2">
            {r.catalogNumber ? `#${r.catalogNumber}` : r.id.slice(0, 8)}
          </Link>
        </span>
      ))}
    </>
  )
}

function Row({ event }: { event: TimelineEvent | LineageEvent }) {
  const when = event.at ? formatDay(String(event.at), event.precision) : 'date unknown'
  const e = event as TimelineEvent
  let icon = <Package className="h-4 w-4" />
  let text: React.ReactNode = null
  switch (event.kind) {
    case 'lineage': {
      const lineage = event as LineageEvent
      icon = <GitBranch className="h-4 w-4" />
      text = lineage.direction === 'into'
        ? <>Cut into <Related event={lineage} /></>
        : lineage.related.length > 1
          ? <>Assembled from <Related event={lineage} /></>
          : <>Cut from <Related event={lineage} /></>
      break
    }
    case 'origin':
      icon = <Sparkles className="h-4 w-4" />
      text = e.planned
        ? <>In place: {e.detail === 'demolition' ? 'demolition' : 'deinstallation'} planned</>
        : <>Entered circulation{e.detail ? `: ${vocabLabel(ORIGIN_KIND_LABELS, e.detail)}` : ''}{e.cycle != null ? ' (earlier cycle)' : ''}</>
      break
    case 'deinstalled':
      icon = <Wrench className="h-4 w-4" />
      text = <>Deinstalled</>
      break
    case 'exit':
      icon = <LogOut className="h-4 w-4" />
      text = <>Left circulation{e.detail ? `: ${vocabLabel(EXIT_KIND_LABELS, e.detail)}` : ''}{e.cycle != null ? ' (earlier cycle)' : ''}</>
      break
    case 'snapshot':
      icon = <Camera className="h-4 w-4" />
      text = (
        <>
          State v{e.version}{e.name ? ` ${e.name}` : ''}
          {e.status && e.status !== 'published' ? `, ${e.status}` : ''}
          {e.corrected ? ', corrected' : ''}
          {e.corrects ? ', a correction' : ''}
          {e.withdrawn ? ', withdrawn' : ''}
        </>
      )
      break
    case 'evidence':
      icon = <FlaskConical className="h-4 w-4" />
      text = e.method ? (
        <>
          {vocabLabel(EVIDENCE_METHOD_LABELS, e.method)}
          {e.quantity ? `: ${quantityLabel(e.quantity)} ${formatResult({ value: e.value, range: e.range, unit: e.unit })}` : ''}
          {e.status && e.status !== 'published' ? `, ${e.status}` : ''}
          {e.corrected ? ', corrected' : ''}
          {e.corrects ? ', a correction' : ''}
          {e.verification && e.verification !== 'unverified'
            ? `, ${vocabLabel(VERIFICATION_STATE_LABELS, e.verification).toLowerCase()}` : ''}
          {e.resolution === 'approximate' ? ' (state approximate)' : ''}
        </>
      ) : <>Evidence record, withdrawn</>
      break
    default:
      icon = <Wrench className="h-4 w-4" />
      text = <>Record changed{e.paths && e.paths.length ? `: ${e.paths.join(', ')}` : ''}</>
  }
  return (
    <li className="flex gap-2 border-l border-border pl-3 text-sm">
      <span className="mt-0.5 shrink-0 text-muted-foreground">{icon}</span>
      <div className="min-w-0">
        <p>{text}</p>
        <p className="text-xs text-muted-foreground">{when}</p>
      </div>
    </li>
  )
}

export default function HistoryList({ events, lineage, layers }: {
  events: TimelineEvent[]
  lineage: LineageEvent[]
  layers: Layers
}) {
  const sections = mergeHistory(events, lineage, layers)
  if (sections.length === 0) return <p className="text-sm text-muted-foreground">Nothing to show with these layers.</p>
  return (
    <div className="space-y-4">
      {sections.map((section) => (
        <div key={section.id} className="space-y-2">
          <div className="flex items-center gap-2">
            <Archive className="h-3.5 w-3.5 text-muted-foreground" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{SECTIONS[section.id]}</h3>
            {section.id !== 'history' && <Badge variant="outline" className="text-[10px]">outside the folded states</Badge>}
          </div>
          <ol className="space-y-2">
            {section.rows.map((event, i) => (
              <Row key={`${event.kind}-${(event as TimelineEvent).record_id ?? i}-${i}`} event={event as TimelineEvent} />
            ))}
          </ol>
        </div>
      ))}
    </div>
  )
}
