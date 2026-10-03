'use client'

/**
 * The records of a rebound hammer or core submission (fan-out, decision
 * 7.1): one card per test area or specimen, the instrument shared. Fields
 * are generated from the registry's payload schema; the grid tool and the
 * pairing of a core with a rebound record (8.42) are the two additions.
 */
import { Copy, Crosshair, Grid3x3, Plus, Trash2 } from 'lucide-react'

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
import { Button } from '@/components/ui/button'
import type { EnvelopeHelp, MethodInfo, ProblemRow, QuantityInfo } from '@/lib/evidence/api'
import { gridPoints, roundVec, type GridSpec } from '@/lib/evidence/grid'
import { layoutOf } from '@/lib/evidence/layout'
import { getAt, parseNumber, setAt, type FormObject, type FormValue } from '@/lib/evidence/schema'
import { isObject } from '@/lib/evidence/schema'
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
  rebounds: CandidateRebound[]
  help: EnvelopeHelp
  onPickPoint: (recordKey: string) => void
  onPickGrid: (recordKey: string) => void
  onAddLocations: () => void
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

export default function RecordsEditor(props: Props) {
  const { idPrefix, method, records, shared, onRecords, onShared, problems, help } = props
  const layout = layoutOf(method.name)
  const isRebound = method.name === 'rebound_hammer'

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

  return (
    <div className="space-y-4">
      {layout.shared.length > 0 && (
        <fieldset className="space-y-3 rounded-md border border-border/70 p-3">
          <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Used for every {layout.recordLabel}
          </legend>
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
        </fieldset>
      )}

      {records.map((record, index) => {
        const rowProblems = problems(index)
        const grid = isRebound ? gridOf(record.payload) : null
        const id = `${idPrefix}-r${index}`
        const hide = [...layout.shared, ...(isRebound ? ['rejected_reading_indices'] : [])]
        return (
          <fieldset key={record.key} className="space-y-3 rounded-md border border-border p-3">
            <legend className="px-1 text-sm font-semibold capitalize">
              {layout.recordLabel} {index + 1}
            </legend>
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
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
                onClick={() => onRecords([...records.slice(0, index + 1), repeatedRecord(method, record), ...records.slice(index + 1)])}>
                <Copy className="mr-1 h-3.5 w-3.5" />Add another like this
              </Button>
              {records.length > 1 && (
                <Button type="button" variant="ghost" size="sm" className="h-8 text-xs text-muted-foreground"
                  onClick={() => onRecords(records.filter((r) => r.key !== record.key))}>
                  <Trash2 className="mr-1 h-3.5 w-3.5" />Remove this {layout.recordLabel}
                </Button>
              )}
            </div>
          </fieldset>
        )
      })}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
          onClick={() => {
            const last = records[records.length - 1]
            onRecords([...records, last ? repeatedRecord(method, last) : { ...repeatedRecord(method, records[0]), key: newKey() }])
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
