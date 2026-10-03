'use client'

/**
 * What happened to a component, merged (spec 4.1, decision 8.68): archived
 * cycles, the origin, every state and correction, every evidence record
 * (before cataloguing, in the history, after the piece left circulation)
 * and the exit, in time order. Loaded when the tab is opened. The backend
 * leaves out what the caller may not see.
 */
import { useEffect, useState } from 'react'
import { Archive, Camera, FlaskConical, Loader2, LogOut, Package, Sparkles, Wrench } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { EVIDENCE_METHOD_LABELS, EXIT_KIND_LABELS, ORIGIN_KIND_LABELS, VERIFICATION_STATE_LABELS, vocabLabel } from '@/generated/Vocab'
import { BackendError, backendJson } from '@/lib/backend'
import { formatResult, quantityLabel } from '@/lib/evidence/format'
import { formatDateAtPrecision } from '@/components/components/componentDetailShared'

type TimelineEvent = {
  kind: 'origin' | 'exit' | 'snapshot' | 'evidence' | 'metadata_changed'
  at?: string | null
  precision?: string | null
  section?: string
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

function Row({ event }: { event: TimelineEvent }) {
  const when = event.at ? formatDateAtPrecision(event.at, event.precision) : 'date unknown'
  let icon = <Package className="h-4 w-4" />
  let text: React.ReactNode = null
  switch (event.kind) {
    case 'origin':
      icon = <Sparkles className="h-4 w-4" />
      text = <>Entered circulation{event.detail ? `: ${vocabLabel(ORIGIN_KIND_LABELS, event.detail)}` : ''}{event.cycle != null ? ' (earlier cycle)' : ''}</>
      break
    case 'exit':
      icon = <LogOut className="h-4 w-4" />
      text = <>Left circulation{event.detail ? `: ${vocabLabel(EXIT_KIND_LABELS, event.detail)}` : ''}{event.cycle != null ? ' (earlier cycle)' : ''}</>
      break
    case 'snapshot':
      icon = <Camera className="h-4 w-4" />
      text = (
        <>
          State v{event.version}{event.name ? ` ${event.name}` : ''}
          {event.status && event.status !== 'published' ? `, ${event.status}` : ''}
          {event.corrected ? ', corrected' : ''}
          {event.corrects ? ', a correction' : ''}
          {event.withdrawn ? ', withdrawn' : ''}
        </>
      )
      break
    case 'evidence':
      icon = <FlaskConical className="h-4 w-4" />
      text = event.method ? (
        <>
          {vocabLabel(EVIDENCE_METHOD_LABELS, event.method)}
          {event.quantity ? `: ${quantityLabel(event.quantity)} ${formatResult({ value: event.value, range: event.range, unit: event.unit })}` : ''}
          {event.status && event.status !== 'published' ? `, ${event.status}` : ''}
          {event.corrected ? ', corrected' : ''}
          {event.corrects ? ', a correction' : ''}
          {event.verification && event.verification !== 'unverified'
            ? `, ${vocabLabel(VERIFICATION_STATE_LABELS, event.verification).toLowerCase()}` : ''}
          {event.resolution === 'approximate' ? ' (state approximate)' : ''}
        </>
      ) : <>Evidence record, withdrawn</>
      break
    default:
      icon = <Wrench className="h-4 w-4" />
      text = <>Record changed{event.paths && event.paths.length ? `: ${event.paths.join(', ')}` : ''}</>
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

export default function TimelineView({ identityId, reloadKey }: { identityId: string; reloadKey: number }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    backendJson<{ events: TimelineEvent[] }>(`/identities/${encodeURIComponent(identityId)}/timeline`)
      .then((body) => { if (!cancelled) { setEvents(body.events); setError(null) } })
      .catch((err) => {
        if (cancelled) return
        setEvents([])
        setError(err instanceof BackendError ? err.message : 'Could not load the timeline.')
      })
    return () => { cancelled = true }
  }, [identityId, reloadKey])

  if (events === null) {
    return <div className="flex justify-center py-4 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin" /></div>
  }
  if (error) return <p className="text-sm text-destructive" role="alert">{error}</p>
  if (events.length === 0) return <p className="text-sm text-muted-foreground">Nothing recorded yet.</p>

  const sections = ['before_cataloguing', 'history', 'after_leaving_circulation']
    .map((id) => ({ id, rows: events.filter((e) => (e.section ?? 'history') === id) }))
    .filter((s) => s.rows.length > 0)

  return (
    <div className="space-y-4">
      {sections.map((section) => (
        <div key={section.id} className="space-y-2">
          <div className="flex items-center gap-2">
            <Archive className="h-3.5 w-3.5 text-muted-foreground" />
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{SECTIONS[section.id]}</h4>
            {section.id !== 'history' && <Badge variant="outline" className="text-[10px]">outside the folded states</Badge>}
          </div>
          <ol className="space-y-2">
            {section.rows.map((event, i) => <Row key={`${event.kind}-${event.record_id ?? i}-${i}`} event={event} />)}
          </ol>
        </div>
      ))}
    </div>
  )
}
