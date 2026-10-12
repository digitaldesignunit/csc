'use client'

/**
 * The records of a rebound hammer or core submission (fan-out, decision 7.1,
 * 8.134 d): the shared settings (the instrument) once, folded, and one row
 * per test area or specimen with its key values, opened one at a time to
 * edit. Fields are generated from the registry's payload schema; the grid
 * tool and the pairing of a core with a rebound record (8.42) are the two
 * additions.
 */
import { useState } from 'react'
import { AlertTriangle, ChevronDown, Copy, Crosshair, Grid3x3, Plus, Trash2 } from 'lucide-react'

import { Field, NativeSelect, NumberList } from '@/components/evidence/controls'
import DerivedField from '@/components/evidence/form/DerivedField'
import PositionField from '@/components/evidence/form/PositionField'
import {
  newKey,
  repeatedRecord,
  type CandidateRebound,
  type RecordState,
} from '@/components/evidence/form/state'
import SchemaFields, { type Override } from '@/components/evidence/SchemaFields'
import { FoldCard } from '@/components/evidence/form/FormShell'
import { Button } from '@/components/ui/button'
import type { EnvelopeHelp, MethodInfo, ProblemRow, QuantityInfo } from '@/lib/evidence/api'
import { gridPoints, roundVec, type GridSpec } from '@/lib/evidence/grid'
import type { SectionState } from '@/lib/evidence/issues'
import { layoutOf } from '@/lib/evidence/layout'
import { recordRow } from '@/lib/evidence/rows'
import { getAt, parseNumber, setAt, type FormObject, type FormValue } from '@/lib/evidence/schema'
import { isBlank, isObject } from '@/lib/evidence/schema'
import { cn } from '@/lib/utils'
import { formatDateAtPrecision } from '@/components/components/componentDetailShared'

/** The grid of a test area as the form holds it, as the tool's spec. */
export function gridOf(payload: FormObject): GridSpec | null {
  const grid = getAt(payload, ['test_area', 'grid'])
  if (!isObject(grid)) return null
  const g = grid as FormObject
  const vec = (v: FormValue | undefined) => {
    const parts = Array.isArray(v) ? v.map((p) => parseNumber(String(p))) : []
    return parts.length === 3 && parts.every((p): p is number => p !== null)
      ? ([parts[0], parts[1], parts[2]] as [number, number, number]) : null
  }
  const origin = vec(g.origin)
  const u = vec(g.u)
  const v = vec(g.v)
  const rows = parseNumber(String(g.rows ?? ''))
  const cols = parseNumber(String(g.cols ?? ''))
  const spacing = parseNumber(String(g.spacing_mm ?? ''))
  if (!origin || !u || !v || !rows || !cols || !spacing) return null
  return { origin, u, v, rows, cols, spacing_mm: spacing }
}

export function gridToForm(grid: GridSpec): FormObject {
  const text = (v: number[]) => v.map(String)
  return {
    origin: text(roundVec(grid.origin, 3)),
    u: text(grid.u),
    v: text(grid.v),
    rows: String(grid.rows),
    cols: String(grid.cols),
    spacing_mm: String(grid.spacing_mm),
  }
}

type Props = {
  idPrefix: string
  method: MethodInfo
  quantities: QuantityInfo[]
  records: RecordState[]
  shared: FormObject
  onRecords: (next: RecordState[]) => void
  onShared: (next: FormObject) => void
  /** problems of the server by record position */
  problems: (index: number) => ProblemRow[]
  /** what is missing in a record, by position (the form's own checks) */
  missing: (index: number) => string[]
  /** how the shared settings stand: done, missing a field, or the server found something */
  sharedState: SectionState
  rebounds: CandidateRebound[]
  help: EnvelopeHelp
  onPickPoint: (recordKey: string) => void
  onPickGrid: (recordKey: string) => void
  onAddLocations: () => void
  /** One record only (a correction, an edit): no copies, no further records. */
  single?: boolean
  /** A record to open (a jump from the summary), by position; changes with every jump. */
  focusRecord?: { index: number; at: number } | null
}

function payloadErrors(rows: ProblemRow[]): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const row of rows) {
    if (!row.path.startsWith('payload.')) continue
    const key = row.path.slice('payload.'.length)
    ;(out[key] ??= []).push(row.message)
  }
  return out
}

function otherErrors(rows: ProblemRow[]): ProblemRow[] {
  return rows.filter((row) => !row.path.startsWith('payload.'))
}

/** How many values of the shared settings are filled, for the folded line. */
function filled(value: FormValue | undefined): number {
  if (value === undefined || value === null) return 0
  if (typeof value === 'string') return value.trim() === '' ? 0 : 1
  if (typeof value === 'boolean') return 0
  if (Array.isArray(value)) return value.reduce<number>((n, v) => n + filled(v), 0)
  return Object.values(value).reduce<number>((n, v) => n + filled(v), 0)
}

export default function RecordsEditor(props: Props) {
  const { idPrefix, method, records, shared, onRecords, onShared, problems, help } = props
  const layout = layoutOf(method.name)
  const isRebound = method.name === 'rebound_hammer'
  const [openKey, setOpenKey] = useState<string | null>(records.length === 1 ? records[0].key : null)
  const [sharedOpen, setSharedOpen] = useState(true)
  const [lastFocus, setLastFocus] = useState<number | null>(null)

  // a jump from the summary opens the record (and the shared settings for -1)
  if (props.focusRecord && props.focusRecord.at !== lastFocus) {
    setLastFocus(props.focusRecord.at)
    const target = records[props.focusRecord.index]
    if (target) setOpenKey(target.key)
  }

  const sharedErrors: Record<string, string[]> = {}
  records.forEach((_, i) => {
    const all = payloadErrors(problems(i))
    for (const [key, messages] of Object.entries(all)) {
      if (layout.shared.some((s) => key === s || key.startsWith(`${s}.`))) {
        sharedErrors[key] = [...new Set([...(sharedErrors[key] ?? []), ...messages])]
      }
    }
  })

  const update = (key: string, patch: Partial<RecordState>) =>
    onRecords(records.map((r) => (r.key === key ? { ...r, ...patch } : r)))

  const recordOverrides = (record: RecordState): Record<string, Override> => ({
    readings: ({ id, parent, setParent, label, resolved, errors }) => (
      <Field id={id} label={label} help={resolved.description} required errors={errors}>
        <NumberList
          id={id}
          values={Array.isArray(parent.readings) ? (parent.readings as string[]) : []}
          onChange={(next) => setParent({ ...parent, readings: next })}
          rejected={Array.isArray(parent.rejected_reading_indices)
            ? (parent.rejected_reading_indices as string[]).map(Number) : []}
          onRejectedChange={(next) => setParent({ ...parent, rejected_reading_indices: next.map(String) })}
        />
      </Field>
    ),
    'test_area.grid': ({ id, label, resolved, errors }) => {
      const grid = gridOf(record.payload)
      const readings = Array.isArray(record.payload.readings) ? record.payload.readings.length : 0
      const area = isObject(record.payload.test_area) ? (record.payload.test_area as FormObject) : {}
      const have = isObject(area.grid)
      return (
        <div className="space-y-2" id={id}>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
              onClick={() => props.onPickGrid(record.key)}>
              <Grid3x3 className="mr-1 h-3.5 w-3.5" />
              {have ? 'Change the impact grid' : 'Lay an impact grid on the model'}
            </Button>
            {have && (
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
                onClick={() => update(record.key, {
                  payload: setAt(record.payload, ['test_area', 'grid'], null),
                  position: { ...record.position, kind: 'none', snapshotId: null, point: null },
                })}>
                <Trash2 className="mr-1 h-3 w-3" />Remove grid
              </Button>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {label}: {resolved.description}
          </p>
          {grid && (
            <p className="text-xs">
              {grid.rows} x {grid.cols} points, {grid.spacing_mm} mm apart ({gridPoints(grid).length} points).
              {' '}
              {readings === grid.rows * grid.cols
                ? 'One reading per point, row by row.'
                : (
                  <span className="text-amber-700 dark:text-amber-300">
                    {readings} readings entered: one reading per point is needed.
                  </span>
                )}
            </p>
          )}
          {errors.length > 0 && (
            <ul role="alert">{errors.map((m) => <li key={m} className="text-xs text-destructive">{m}</li>)}</ul>
          )}
        </div>
      )
    },
    'sampling.paired_rebound_id': ({ id, label, resolved, parent, setParent, errors }) => {
      const taken = records.filter((r) => r.key !== record.key)
        .map((r) => String(getAt(r.payload, ['sampling', 'paired_rebound_id']) ?? '')).filter(Boolean)
      const coredAt = String(getAt(record.payload, ['sampling', 'cored_at']) ?? '')
      const value = String(parent.paired_rebound_id ?? '')
      const options = props.rebounds
        .filter((r) => !taken.includes(r.id))
        .filter((r) => !coredAt || Date.parse(r.observedAt) <= Date.parse(coredAt.length === 10 ? `${coredAt}T23:59:59Z` : coredAt))
        .map((r) => ({
          value: r.id,
          label: `${r.label}, ${formatDateAtPrecision(r.observedAt, r.precision)}${r.median !== null ? `, median ${r.median}` : ''}${r.status === 'published' ? '' : ` (${r.status})`}`,
        }))
      return (
        <Field id={id} label={label} help={resolved.description} errors={errors}>
          <NativeSelect
            id={id}
            value={value}
            onChange={(next) => setParent({ ...parent, paired_rebound_id: next })}
            placeholder={options.length ? 'Not paired' : 'No rebound record of this piece fits'}
            options={options}
          />
        </Field>
      )
    },
  })

  /** The fields of one record: opened from its row, or alone when there is only one. */
  const editor = (record: RecordState, index: number) => {
    const rowProblems = problems(index)
    const grid = isRebound ? gridOf(record.payload) : null
    const id = `${idPrefix}-r${index}`
    const hide = [...layout.shared, ...(isRebound ? ['rejected_reading_indices'] : [])]
    return (
      <div className="space-y-3">
        {otherErrors(rowProblems).length > 0 && (
          <ul role="alert" className="space-y-0.5">
            {otherErrors(rowProblems).map((row, i) => (
              <li key={i} className="text-xs text-destructive">
                {row.path ? `${row.path}: ` : ''}{row.message}
              </li>
            ))}
          </ul>
        )}
        <SchemaFields
          schema={method.payload_schema}
          root={method.payload_schema}
          value={record.payload}
          onChange={(payload) => update(record.key, { payload })}
          idPrefix={id}
          layout={layout}
          errors={payloadErrors(rowProblems)}
          hide={hide}
          overrides={recordOverrides(record)}
        />
        <PositionField
          id={`${id}-position`}
          position={record.position}
          onChange={(position) => update(record.key, { position })}
          onPick={() => props.onPickPoint(record.key)}
          gridCentre={grid !== null}
          required={method.position_required}
          errors={rowProblems.filter((p) => p.path.startsWith('position')).map((p) => p.message)}
          help={help('PositionInput', 'description')}
        />
        <DerivedField
          id={`${id}-derived`}
          method={method}
          quantities={props.quantities}
          value={record.derived}
          onChange={(derived) => update(record.key, { derived })}
          errors={rowProblems.filter((p) => p.path.startsWith('derived')).map((p) => p.message)}
        />
        {!props.single && (
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
              onClick={() => {
                const copy = repeatedRecord(method, record)
                onRecords([...records.slice(0, index + 1), copy, ...records.slice(index + 1)])
                setOpenKey(copy.key)
              }}>
              <Copy className="mr-1 h-3.5 w-3.5" />Add another like this
            </Button>
            {records.length > 1 && (
              <Button type="button" variant="ghost" size="sm" className="h-8 text-xs text-muted-foreground"
                onClick={() => { onRecords(records.filter((r) => r.key !== record.key)); setOpenKey(null) }}>
                <Trash2 className="mr-1 h-3.5 w-3.5" />Remove this {layout.recordLabel}
              </Button>
            )}
          </div>
        )}
      </div>
    )
  }

  const sharedBlock = layout.shared.length > 0 && (
    <FoldCard
      title={`Used for every ${layout.recordLabel}`}
      open={sharedOpen}
      onOpenChange={setSharedOpen}
      state={props.sharedState}
      summary={`${filled(shared)} value${filled(shared) === 1 ? '' : 's'} filled in`}
    >
      <SchemaFields
        schema={method.payload_schema}
        root={method.payload_schema}
        value={shared}
        onChange={onShared}
        idPrefix={`${idPrefix}-shared`}
        layout={layout}
        errors={sharedErrors}
        only={layout.shared}
      />
    </FoldCard>
  )

  if (props.single && records[0]) {
    return (
      <div className="space-y-4">
        {sharedBlock}
        {editor(records[0], 0)}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {sharedBlock}

      <div className="overflow-hidden rounded-md border border-border">
        <div className="hidden grid-cols-[2.5rem_minmax(0,1.2fr)_minmax(0,1.5fr)_minmax(0,1.5fr)_1.5rem] items-center gap-3 border-b border-border bg-muted/40 px-3 py-1.5 text-xs font-medium text-muted-foreground sm:grid">
          <span>#</span><span className="capitalize">{layout.recordLabel}</span><span>Where</span><span>Values</span><span />
        </div>
        <ul className="divide-y divide-border">
          {records.map((record, index) => {
            const row = recordRow(method.name, record, index)
            const isOpen = openKey === record.key
            const missing = props.missing(index)
            const server = problems(index)
            const flagged = missing.length + server.length
            const empty = isBlank(record.payload.readings) && isBlank(getAt(record.payload, ['specimen', 'measured_diameter_mm']))
            return (
              <li key={record.key} id={`${idPrefix}-row-${index}`} className={cn(isOpen && 'bg-muted/20')}>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpenKey(isOpen ? null : record.key)}
                  className="grid w-full grid-cols-[2rem_minmax(0,1fr)_1.5rem] items-center gap-x-3 gap-y-0.5 px-3 py-2 text-left sm:grid-cols-[2.5rem_minmax(0,1.2fr)_minmax(0,1.5fr)_minmax(0,1.5fr)_1.5rem]"
                >
                  <span className="row-span-2 self-center text-sm font-semibold tabular-nums text-muted-foreground sm:row-span-1">
                    {index + 1}
                  </span>
                  <span className="min-w-0 truncate text-sm font-medium">{row.title}</span>
                  <span className="col-start-3 row-start-1 flex justify-end sm:col-start-5">
                    {flagged > 0 && !empty ? (
                      <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" aria-label={`${flagged} to look at`} />
                    ) : (
                      <ChevronDown className={cn('h-4 w-4 text-muted-foreground transition-transform', !isOpen && '-rotate-90')} aria-hidden />
                    )}
                  </span>
                  <span className="col-start-2 min-w-0 truncate text-xs text-muted-foreground sm:col-start-3 sm:text-sm">
                    {row.where || <span className="italic">no place yet</span>}
                  </span>
                  <span className="col-start-2 min-w-0 truncate text-xs text-muted-foreground sm:col-start-4 sm:text-sm">
                    {row.facts.join('; ')}
                  </span>
                </button>
                {isOpen && <div className="border-t border-border/60 bg-background px-3 py-3">{editor(record, index)}</div>}
              </li>
            )
          })}
        </ul>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
          onClick={() => {
            const last = records[records.length - 1]
            const fresh = last ? repeatedRecord(method, last) : { ...repeatedRecord(method, records[0]), key: newKey() }
            onRecords([...records, fresh])
            setOpenKey(fresh.key)
          }}>
          <Plus className="mr-1 h-3.5 w-3.5" />Add a {layout.recordLabel}
        </Button>
        <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={props.onAddLocations}>
          <Crosshair className="mr-1 h-3.5 w-3.5" />Add test locations from a grid on the model
        </Button>
      </div>
    </div>
  )
}
