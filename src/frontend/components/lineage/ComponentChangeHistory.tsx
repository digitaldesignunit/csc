'use client'

/**
 * The change log of a component, its snapshots and its evidence (spec
 * section 3.8, I30; decision 8.36). Members of the dataset only: old
 * values may name people. Loaded when opened.
 */
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { History, Loader2 } from 'lucide-react'

import type { ChangeLogEntryView } from '@/generated/LineageModels'
import { CHANGE_CAUSE_LABELS, vocabLabel } from '@/generated/Vocab'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import { BackendError, backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'
import { sameJson } from '@/lib/lineage'
import { formatTimestamp } from '@/lib/utils'

const FROM_ANOTHER_COMPONENT = new Set(['inherited_from_parent', 'derived_exit', 'withdraw'])

function shown(value: unknown): string {
  if (value === null || value === undefined || value === '') return '---'
  if (typeof value === 'string') return value
  const json = JSON.stringify(value)
  return json.length > 160 ? `${json.slice(0, 157)}...` : json
}

type Change = { path: string; old?: unknown; new?: unknown }

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

/** A change of a nested block as the subfields that differ (origin.place.name, ...). */
function expand(change: Change): Change[] {
  const { old: before, new: after } = change
  if (!isRecord(before) || !isRecord(after)) return [change]
  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])].sort()
  return keys.flatMap((key) =>
    sameJson(before[key] ?? null, after[key] ?? null)
      ? []
      : expand({ path: `${change.path}.${key}`, old: before[key], new: after[key] }))
}

type Props = {
  identityId: string
  dataset: string | null | undefined
  /** snapshot id --> version, to name the snapshot an entry is about */
  versions: Record<string, number>
}

export default function ComponentChangeHistory({ identityId, dataset, versions }: Props) {
  const { me, rolesIn } = useMe()
  const [open, setOpen] = useState(false)
  const [entries, setEntries] = useState<ChangeLogEntryView[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const member = !!me && rolesIn(dataset).length > 0

  useEffect(() => {
    if (!open || entries !== null || !member) return
    let cancelled = false
    backendJson<ChangeLogEntryView[]>(`/identities/${identityId}/changes`)
      .then((rows) => { if (!cancelled) setEntries(rows) })
      .catch((err) => {
        if (cancelled) return
        setEntries([])
        setError(err instanceof BackendError ? err.message : 'Could not load the history.')
      })
    return () => { cancelled = true }
  }, [open, entries, member, identityId])

  if (!member) return null

  const subject = (entry: ChangeLogEntryView) => {
    if (entry.record_kind === 'identity') return 'Component'
    if (entry.record_kind === 'snapshot') {
      const version = versions[entry.record_id]
      return version === undefined ? 'Snapshot' : `Snapshot v${version}`
    }
    return 'Evidence'
  }

  return (
    <Accordion type="single" collapsible className="w-full rounded-lg border border-border/60"
      onValueChange={(value) => setOpen(value === 'history')}>
      <AccordionItem value="history" className="border-0">
        <AccordionTrigger className="px-3 py-2.5 text-sm">
          <span className="flex items-center gap-2"><History className="h-4 w-4" />Change history</span>
        </AccordionTrigger>
        <AccordionContent className="px-3 pb-3 pt-0">
          {entries === null ? (
            <div className="flex justify-center py-3 text-muted-foreground">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>
          ) : error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : entries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No changes since the catalog moved to its new data model.
            </p>
          ) : (
            <ol className="max-h-96 space-y-2 overflow-y-auto pr-1">
              {entries.map((entry) => (
                <li key={entry._id} className="rounded-md border border-border/60 p-2 text-xs">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-2">
                    <span className="font-semibold">
                      {vocabLabel(CHANGE_CAUSE_LABELS, entry.cause)}
                      <span className="font-normal text-muted-foreground"> --- {subject(entry)}</span>
                    </span>
                    <span className="text-muted-foreground">
                      {formatTimestamp(entry.at)}{entry.by_username ? `, ${entry.by_username}` : ''}
                    </span>
                  </div>
                  {entry.source_record_id && FROM_ANOTHER_COMPONENT.has(entry.cause)
                    && entry.source_record_id !== identityId && (
                    <p className="text-muted-foreground">
                      Because of{' '}
                      <Link href={`/components/${entry.source_record_id}`} className="font-mono underline underline-offset-2">
                        {entry.source_record_id.slice(0, 8)}
                      </Link>
                    </p>
                  )}
                  <ul className="mt-1 space-y-0.5">
                    {entry.changes.flatMap(expand).map((change) => (
                      <li key={change.path} className="break-words">
                        <span className="font-mono">{change.path}</span>:{' '}
                        <span className="text-muted-foreground line-through decoration-muted-foreground/50">{shown(change.old)}</span>
                        {' --> '}
                        <span>{shown(change.new)}</span>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ol>
          )}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
