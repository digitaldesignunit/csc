'use client'

/**
 * The method choice (decision 8.134 b): the methods in groups (strength,
 * non-destructive, inspection, reinforcement, documents) with a search; once
 * one is chosen the list folds to a chip with "Change".
 */
import { useEffect, useState } from 'react'
import { Pencil, Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EVIDENCE_METHOD_LABELS, vocabLabel } from '@/generated/Vocab'
import type { MethodInfo } from '@/lib/evidence/api'
import { groupMethods, searchMethods } from '@/lib/evidence/methodGroups'
import { tierChip } from '@/lib/evidence/order'
import { cn } from '@/lib/utils'

/** The method's description, or nothing when it only repeats its name. */
export function describes(method: MethodInfo): string {
  const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase()
  const text = method.description ?? ''
  return !text.trim() || same(text, method.label) || same(text, vocabLabel(EVIDENCE_METHOD_LABELS, method.name))
    ? ''
    : text
}

export function firstSentence(text: string): string {
  const end = text.search(/\.\s/)
  return end > 0 ? text.slice(0, end + 1) : text
}

function TierChip({ method }: { method: MethodInfo }) {
  const chip = tierChip(method.source_tier, method.tier_from_payload)
  return chip ? (
    <span className="shrink-0 rounded-full border border-border px-2 py-0.5 text-[10px] text-muted-foreground">{chip}</span>
  ) : null
}

export default function MethodPicker({
  methods,
  value,
  onPick,
  locked,
}: {
  methods: MethodInfo[]
  value: string | null
  onPick: (name: string) => void
  /** a correction keeps the method of the record it replaces */
  locked?: boolean
}) {
  const [open, setOpen] = useState(value === null)
  const [query, setQuery] = useState('')
  // a method chosen from outside (repeat from my last record) folds the list
  useEffect(() => { if (value) setOpen(false) }, [value])
  const chosen = methods.find((m) => m.name === value) ?? null

  if (chosen && (!open || locked)) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-primary/40 bg-primary/5 px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {vocabLabel(EVIDENCE_METHOD_LABELS, chosen.name)}
            <TierChip method={chosen} />
          </p>
          {describes(chosen) && (
            <p className="mt-0.5 text-xs text-muted-foreground">{describes(chosen)}</p>
          )}
        </div>
        {!locked && (
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => setOpen(true)}>
            <Pencil className="mr-1 h-3.5 w-3.5" />Change
          </Button>
        )}
      </div>
    )
  }

  const found = searchMethods(methods, query)
  const groups = groupMethods(found)
  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
        <Input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search: rebound, drawing, cracks, datasheet ..."
          aria-label="Search the methods"
          className="pl-8"
        />
      </div>
      {groups.length === 0 && (
        <p className="text-sm text-muted-foreground" role="status">No method fits &quot;{query}&quot;.</p>
      )}
      <div role="radiogroup" aria-label="Evidence method" className="space-y-3">
        {groups.map((group) => (
          <div key={group.id} className="space-y-1.5">
            <p className="flex flex-wrap items-baseline gap-2">
              <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group.title}</span>
              {group.hint && <span className="text-xs text-muted-foreground/80">{group.hint}</span>}
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {group.methods.map((m) => {
                const active = value === m.name
                return (
                  <button
                    key={m.name}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => { onPick(m.name); setOpen(false); setQuery('') }}
                    className={cn(
                      'rounded-lg border p-3 text-left text-sm transition-colors',
                      group.methods.length === 1 && 'sm:col-span-2',
                      active ? 'border-primary bg-primary/5 ring-1 ring-primary/30' : 'border-border hover:bg-muted/40',
                    )}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="font-medium">{vocabLabel(EVIDENCE_METHOD_LABELS, m.name)}</span>
                      <TierChip method={m} />
                    </span>
                    {describes(m) && (
                      <span className="mt-1 line-clamp-2 block text-xs text-muted-foreground">{firstSentence(describes(m))}</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      {chosen && (
        <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" onClick={() => setOpen(false)}>
          Keep {vocabLabel(EVIDENCE_METHOD_LABELS, chosen.name)}
        </Button>
      )}
    </div>
  )
}
