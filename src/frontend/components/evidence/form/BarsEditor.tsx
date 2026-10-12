'use client'

/**
 * The bars of a reinforcement layout (decision 8.134 h): collapsed rows (the
 * index, diameter, steel grade, cover, number of points, problems), one
 * expanded at a time, "expand all" / "collapse all", and bulk edits for
 * diameter and grade across selected bars. The points of a bar stay editable
 * as text inside the expanded row. A layout from Grasshopper has dozens of
 * bars: the table makes them readable and the bulk edit makes them quick.
 */
import { useMemo, useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronsDownUp, ChevronsUpDown, Plus, Trash2 } from 'lucide-react'

import { Field } from '@/components/evidence/controls'
import { PointsField } from '@/components/evidence/SchemaFields'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { barRow, barsWithProblems, removeBars, setOnBars } from '@/lib/evidence/rows'
import type { FormObject } from '@/lib/evidence/schema'
import { parseNumber } from '@/lib/evidence/schema'
import { cn } from '@/lib/utils'

const NEW_BAR: FormObject = { spec: '', diameter_mm: '', diameter_known: true, cover_mm: '', points: [] }

export default function BarsEditor({
  id,
  bars,
  onChange,
  serverErrors,
  helpFor,
  focusBar,
}: {
  id: string
  bars: FormObject[]
  onChange: (next: FormObject[]) => void
  /** what the server said about the bars */
  serverErrors?: string[]
  helpFor?: (field: string) => string
  /** a bar to open (a jump from the summary) */
  focusBar?: number | null
}) {
  const [open, setOpen] = useState<Set<number>>(() => new Set())
  const [selected, setSelected] = useState<Set<number>>(() => new Set())
  const [onlyProblems, setOnlyProblems] = useState(false)
  const [bulkDiameter, setBulkDiameter] = useState('')
  const [bulkGrade, setBulkGrade] = useState('')
  const [lastFocus, setLastFocus] = useState<number | null | undefined>(undefined)

  // a jump from the summary opens that bar (once per jump)
  if (focusBar !== lastFocus) {
    setLastFocus(focusBar)
    if (focusBar !== null && focusBar !== undefined && focusBar < bars.length) setOpen(new Set([focusBar]))
  }

  const rows = useMemo(() => bars.map((bar, index) => barRow(bar, index)), [bars])
  const problemIndices = useMemo(() => new Set(barsWithProblems(bars)), [bars])
  const shown = rows.map((row, index) => ({ row, index })).filter(({ index }) => !onlyProblems || problemIndices.has(index))

  const toggle = (index: number) => {
    setOpen((prev) => {
      if (prev.has(index)) {
        const next = new Set(prev)
        next.delete(index)
        return next
      }
      // one at a time, unless "expand all" opened several
      return prev.size <= 1 ? new Set([index]) : new Set([...prev, index])
    })
  }
  const update = (index: number, patch: FormObject) =>
    onChange(bars.map((bar, i) => (i === index ? { ...bar, ...patch } : bar)))
  const toggleSelected = (index: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })

  const diameterOk = bulkDiameter.trim() !== '' && (parseNumber(bulkDiameter) ?? 0) > 0

  return (
    <div id={id} className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
          onClick={() => { onChange([...bars, { ...NEW_BAR, points: [] }]); setOpen(new Set([bars.length])) }}>
          <Plus className="mr-1 h-3.5 w-3.5" />Add a bar
        </Button>
        <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" disabled={bars.length === 0}
          onClick={() => setOpen(new Set(bars.map((_, i) => i)))}>
          <ChevronsUpDown className="mr-1 h-3.5 w-3.5" />Expand all
        </Button>
        <Button type="button" variant="ghost" size="sm" className="h-8 text-xs" disabled={open.size === 0}
          onClick={() => setOpen(new Set())}>
          <ChevronsDownUp className="mr-1 h-3.5 w-3.5" />Collapse all
        </Button>
        {problemIndices.size > 0 && (
          <Button type="button" variant={onlyProblems ? 'secondary' : 'ghost'} size="sm" className="h-8 text-xs"
            aria-pressed={onlyProblems} onClick={() => setOnlyProblems(!onlyProblems)}>
            <AlertTriangle className="mr-1 h-3.5 w-3.5 text-amber-600" />
            {onlyProblems ? 'Show all bars' : `Only the ${problemIndices.size} with problems`}
          </Button>
        )}
        <span className="ml-auto text-xs text-muted-foreground">
          {bars.length} bar{bars.length === 1 ? '' : 's'}{selected.size > 0 ? `, ${selected.size} selected` : ''}
        </span>
      </div>

      {selected.size > 0 && (
        <div className="space-y-2 rounded-md border border-primary/40 bg-primary/5 p-3" role="group" aria-label="Change the selected bars">
          <p className="text-xs font-medium">Change the {selected.size} selected bar{selected.size === 1 ? '' : 's'}</p>
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex items-end gap-1.5">
              <div className="space-y-1">
                <label htmlFor={`${id}-bulk-diameter`} className="text-xs">Diameter mm</label>
                <Input id={`${id}-bulk-diameter`} inputMode="decimal" className="h-8 w-24" value={bulkDiameter}
                  onChange={(e) => setBulkDiameter(e.target.value)} />
              </div>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" disabled={!diameterOk}
                onClick={() => onChange(setOnBars(bars, selected, 'diameter_mm', String(parseNumber(bulkDiameter))))}>
                Set diameter
              </Button>
            </div>
            <div className="flex items-end gap-1.5">
              <div className="space-y-1">
                <label htmlFor={`${id}-bulk-grade`} className="text-xs">Steel grade</label>
                <Input id={`${id}-bulk-grade`} className="h-8 w-32" placeholder="BSt III" value={bulkGrade}
                  onChange={(e) => setBulkGrade(e.target.value)} />
              </div>
              <Button type="button" size="sm" variant="outline" className="h-8 text-xs" disabled={bulkGrade.trim() === ''}
                onClick={() => onChange(setOnBars(bars, selected, 'spec', bulkGrade.trim()))}>
                Set grade
              </Button>
            </div>
            <Button type="button" size="sm" variant="ghost" className="h-8 text-xs text-destructive"
              onClick={() => { onChange(removeBars(bars, selected)); setSelected(new Set()); setOpen(new Set()) }}>
              <Trash2 className="mr-1 h-3.5 w-3.5" />Remove selected
            </Button>
            <Button type="button" size="sm" variant="ghost" className="h-8 text-xs" onClick={() => setSelected(new Set())}>
              Clear selection
            </Button>
          </div>
        </div>
      )}

      {serverErrors && serverErrors.length > 0 && (
        <ul role="alert" className="space-y-0.5">
          {serverErrors.map((m) => <li key={m} className="text-xs text-destructive">{m}</li>)}
        </ul>
      )}

      {bars.length === 0 ? (
        <p className="rounded-md border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
          No bars yet. Add one, or record the layout from Grasshopper and edit the draft here.
        </p>
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <div className="hidden grid-cols-[2rem_4.5rem_6rem_1fr_5rem_4.5rem_1.5rem] items-center gap-2 border-b border-border bg-muted/40 px-2 py-1.5 text-xs font-medium text-muted-foreground sm:grid">
            <Checkbox
              aria-label="Select all bars"
              checked={selected.size === bars.length && bars.length > 0 ? true : selected.size > 0 ? 'indeterminate' : false}
              onCheckedChange={(on) => setSelected(on === true ? new Set(bars.map((_, i) => i)) : new Set())}
            />
            <span>Bar</span><span>Diameter</span><span>Steel grade</span><span>Cover</span><span>Points</span><span />
          </div>
          <ul className="divide-y divide-border">
            {shown.map(({ row, index }) => {
              const bar = bars[index]
              const isOpen = open.has(index)
              const bad = row.problems.length > 0
              return (
                <li key={index} className={cn(isOpen && 'bg-muted/20')}>
                  <div className="grid grid-cols-[2rem_1fr_1.5rem] items-center gap-2 px-2 py-1.5 sm:grid-cols-[2rem_4.5rem_6rem_1fr_5rem_4.5rem_1.5rem]">
                    <Checkbox aria-label={`Select ${row.title}`} checked={selected.has(index)}
                      onCheckedChange={() => toggleSelected(index)} />
                    <button type="button" aria-expanded={isOpen} onClick={() => toggle(index)}
                      className="col-start-2 flex min-w-0 items-center gap-2 text-left text-sm sm:contents">
                      <span className="font-medium">{row.title}</span>
                      <span className="truncate text-muted-foreground sm:hidden">
                        {[row.diameter, row.grade, row.cover && `cover ${row.cover}`, `${row.points} pts`].filter(Boolean).join(' - ')}
                      </span>
                      <span className="hidden tabular-nums sm:inline">{row.diameter || '-'}</span>
                      <span className="hidden truncate sm:inline">{row.grade || '-'}</span>
                      <span className="hidden tabular-nums sm:inline">{row.cover || '-'}</span>
                      <span className="hidden tabular-nums sm:inline">{row.points}</span>
                    </button>
                    <span className="col-start-3 flex items-center justify-end sm:col-start-7">
                      {bad ? (
                        <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" aria-label={row.problems.join(' ')} />
                      ) : (
                        <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', !isOpen && '-rotate-90')} aria-hidden />
                      )}
                    </span>
                  </div>
                  {isOpen && (
                    <div className="space-y-3 border-t border-border/60 bg-background px-3 py-3">
                      {bad && (
                        <ul role="alert" className="space-y-0.5">
                          {row.problems.map((m) => <li key={m} className="text-xs text-destructive">{m}</li>)}
                        </ul>
                      )}
                      <div className="grid gap-3 sm:grid-cols-3">
                        <Field id={`${id}-${index}-spec`} label="Steel grade" help={helpFor?.('spec')}>
                          <Input id={`${id}-${index}-spec`} value={String(bar.spec ?? '')} placeholder="BSt III"
                            onChange={(e) => update(index, { spec: e.target.value })} />
                        </Field>
                        <Field id={`${id}-${index}-diameter_mm`} label="Diameter mm" required help={helpFor?.('diameter_mm')}>
                          <Input id={`${id}-${index}-diameter_mm`} inputMode="decimal" value={String(bar.diameter_mm ?? '')}
                            onChange={(e) => update(index, { diameter_mm: e.target.value })} />
                        </Field>
                        <Field id={`${id}-${index}-cover_mm`} label="Cover mm" help={helpFor?.('cover_mm')}>
                          <Input id={`${id}-${index}-cover_mm`} inputMode="decimal" value={String(bar.cover_mm ?? '')}
                            onChange={(e) => update(index, { cover_mm: e.target.value })} />
                        </Field>
                      </div>
                      <div className="flex items-center gap-2">
                        <Checkbox id={`${id}-${index}-known`} checked={bar.diameter_known !== false}
                          onCheckedChange={(on) => update(index, { diameter_known: on === true })} />
                        <label htmlFor={`${id}-${index}-known`} className="text-sm">
                          The diameter is known (from a drawing or an exposed bar), not assumed
                        </label>
                      </div>
                      <Field id={`${id}-${index}-points`} label="Points" required help={helpFor?.('points')}>
                        <PointsField
                          id={`${id}-${index}-points`}
                          value={Array.isArray(bar.points) ? (bar.points as string[][]) : []}
                          onChange={(points) => update(index, { points })}
                        />
                      </Field>
                      <Button type="button" variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
                        onClick={() => { onChange(bars.filter((_, i) => i !== index)); setOpen(new Set()); setSelected(new Set()) }}>
                        <Trash2 className="mr-1 h-3 w-3" />Remove {row.title.toLowerCase()}
                      </Button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
