'use client'

/**
 * The claim of an archival document, a datasheet or a rule of thumb: the
 * headline result (what the document says) and the pieces it applies to
 * (decision 7.1: one claim, one record per selected piece).
 */
import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { Field, NativeSelect } from '@/components/evidence/controls'
import type { SummaryState } from '@/components/evidence/form/state'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import { BackendError, backendJson } from '@/lib/backend'
import type { MethodInfo, QuantityInfo } from '@/lib/evidence/api'
import { quantityLabel } from '@/lib/evidence/format'
import { uuidFromScan } from '@/lib/scanIds'

export function SummaryEditor({
  id,
  method,
  quantities,
  value,
  onChange,
  errors,
  helpFor,
}: {
  id: string
  method: MethodInfo
  quantities: QuantityInfo[]
  value: SummaryState
  onChange: (next: SummaryState) => void
  errors?: string[]
  helpFor: (field: string) => string
}) {
  const options = method.summary_quantities
    .map((name) => quantities.find((q) => q.name === name))
    .filter((q): q is QuantityInfo => !!q)
  const quantity = options.find((q) => q.name === value.quantity)
  const scalar = quantity?.kind === 'scalar'

  return (
    <fieldset className="space-y-3 rounded-md border border-border/70 p-3">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        What the {method.label.toLowerCase()} says{method.summary_optional ? ' (optional)' : ''}
      </legend>
      <Field
        id={`${id}-quantity`}
        label="Property"
        help={method.summary_optional
          ? 'Leave empty to record the document only: it documents the piece and states no value.'
          : helpFor('quantity')}
        required={!method.summary_optional}
        errors={errors}
      >
        <NativeSelect
          id={`${id}-quantity`}
          value={value.quantity}
          onChange={(next) => {
            const picked = options.find((q) => q.name === next)
            onChange({
              quantity: next, value: '', low: '', high: '', classes: [],
              unit: picked?.unit && picked.unit !== '1' ? picked.unit : '',
            })
          }}
          options={options.map((q) => ({ value: q.name, label: quantityLabel(q.name) }))}
          placeholder={method.summary_optional ? 'None: the document only' : undefined}
        />
      </Field>
      {quantity && scalar && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Field id={`${id}-low`} label="From" help={helpFor('range')}>
              <Input id={`${id}-low`} inputMode="decimal" value={value.low}
                onChange={(e) => onChange({ ...value, low: e.target.value })} />
            </Field>
            <Field id={`${id}-high`} label="To">
              <Input id={`${id}-high`} inputMode="decimal" value={value.high}
                onChange={(e) => onChange({ ...value, high: e.target.value })} />
            </Field>
          </div>
          <Field id={`${id}-value`} label="Single value" help={helpFor('value')}>
            <Input id={`${id}-value`} inputMode="decimal" value={value.value}
              onChange={(e) => onChange({ ...value, value: e.target.value })} />
          </Field>
          {quantity.accepted_units && quantity.accepted_units.length > 1 && (
            <Field id={`${id}-unit`} label="Unit" help={helpFor('unit')}>
              <NativeSelect
                id={`${id}-unit`}
                value={value.unit}
                onChange={(next) => onChange({ ...value, unit: next })}
                options={quantity.accepted_units.map((u) => ({ value: u, label: u }))}
              />
            </Field>
          )}
        </>
      )}
      {quantity && !scalar && (
        <Field
          id={`${id}-classes`}
          label={quantity.values ? 'Classes' : 'Values'}
          help={helpFor('range')}
          required
        >
          {quantity.values ? (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Classes">
              {quantity.values.map((c) => {
                const on = value.classes.includes(c)
                return (
                  <button
                    key={c}
                    type="button"
                    aria-pressed={on}
                    onClick={() => onChange({
                      ...value,
                      classes: on ? value.classes.filter((x) => x !== c) : [...value.classes, c],
                    })}
                    className={`rounded-md border px-2 py-1 text-xs ${
                      on ? 'border-primary bg-primary/10 font-medium' : 'border-border hover:bg-muted/50'
                    }`}
                  >
                    {c}
                  </button>
                )
              })}
            </div>
          ) : (
            <Input
              id={`${id}-classes`}
              placeholder="e.g. B225 (comma separated)"
              value={value.classes.join(', ')}
              onChange={(e) => onChange({
                ...value,
                classes: e.target.value.split(',').map((t) => t.trim()).filter(Boolean),
              })}
            />
          )}
        </Field>
      )}
    </fieldset>
  )
}

type PieceRow = Pick<CatalogShallowRow, 'catalog_number' | 'name'>

export function PiecesField({
  pieces,
  onChange,
  thisPiece,
}: {
  pieces: string[]
  onChange: (next: string[]) => void
  thisPiece: string
}) {
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [rows, setRows] = useState<Record<string, PieceRow | null>>({})

  useEffect(() => {
    let cancelled = false
    for (const id of pieces) {
      if (id in rows) continue
      backendJson<PieceRow>(`/identities/${encodeURIComponent(id)}`)
        .then((row) => { if (!cancelled) setRows((prev) => ({ ...prev, [id]: row })) })
        .catch(() => { if (!cancelled) setRows((prev) => ({ ...prev, [id]: null })) })
    }
    return () => { cancelled = true }
  }, [pieces, rows])

  const add = async () => {
    const id = uuidFromScan(draft)
    if (!id) {
      setError('Paste a component id or a link that ends in one.')
      return
    }
    if (pieces.includes(id)) {
      setError('That piece is already in the list.')
      return
    }
    try {
      await backendJson(`/identities/${encodeURIComponent(id)}`)
    } catch (err) {
      setError(err instanceof BackendError ? err.message : 'Could not find that piece.')
      return
    }
    setError(null)
    setDraft('')
    onChange([...pieces, id])
  }

  return (
    <fieldset className="space-y-2 rounded-md border border-border/70 p-3">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Pieces this applies to
      </legend>
      <p className="text-xs text-muted-foreground">
        One record is made for every piece, each with the same claim. Add the others by id, link or scanned tag.
      </p>
      <ul className="space-y-1">
        {pieces.map((id) => {
          const row = rows[id]
          return (
            <li key={id} className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1.5 text-sm">
              <span className="min-w-0 truncate">
                {row ? `#${row.catalog_number ?? '?'} ${row.name ?? ''}` : id}
                {id === thisPiece && <span className="ml-2 text-xs text-muted-foreground">(this piece)</span>}
              </span>
              {id !== thisPiece && (
                <Button type="button" variant="ghost" size="icon" className="h-7 w-7"
                  onClick={() => onChange(pieces.filter((p) => p !== id))} aria-label="Remove piece">
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </li>
          )
        })}
      </ul>
      <div className="flex gap-2">
        <Input
          value={draft}
          placeholder="Component id or link"
          aria-label="Component id or link"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); void add() } }}
        />
        <Button type="button" variant="outline" onClick={() => void add()} disabled={!draft.trim()}>
          <Plus className="mr-1 h-4 w-4" />Add
        </Button>
      </div>
      {error && <p className="text-xs text-destructive" role="alert">{error}</p>}
    </fieldset>
  )
}
