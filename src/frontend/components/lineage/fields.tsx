'use client'

/**
 * Form fields of the provenance, circulation and cut forms: vocabulary
 * selects, a date with its precision, a DGNB class, and the origin block
 * (spec section 3.1.1, section 2.11; decisions 8.38, I16).
 */
import type { ReactNode } from 'react'

import type { CircularityClass, ConstructionWork, Origin } from '@/generated/CatalogModels'
import {
  CONNECTION_TYPE_LABELS,
  CONSTRUCTION_METHOD_LABELS,
  DGNB_CLASS_LABELS,
  ORIGIN_KIND_LABELS,
  PRECISION_LABELS,
  type ConnectionType,
  type ConstructionMethod,
  type DgnbClass,
} from '@/generated/Vocab'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { OptionalDateInput } from '@/components/ui/optional-date-input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { dateOnlyToIso, isoToDateOnly, WORKS_ORIGIN_KINDS } from '@/lib/lineage'
import { cn } from '@/lib/utils'

const NONE = '__none__'

export function Field({ label, htmlFor, hint, children, className }: {
  label: string
  htmlFor?: string
  hint?: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

export function VocabSelect<T extends string>({ id, labels, value, onChange, allowNone, noneLabel = 'Not stated', disabled, values }: {
  id?: string
  labels: Record<T, string>
  value: T | null | undefined
  onChange: (value: T | null) => void
  allowNone?: boolean
  noneLabel?: string
  disabled?: boolean
  /** Restrict the offered values (default: every key of `labels`). */
  values?: readonly T[]
}) {
  const options = values ?? (Object.keys(labels) as T[])
  return (
    <Select
      value={value ?? NONE}
      onValueChange={(next) => onChange(next === NONE ? null : (next as T))}
      disabled={disabled}
    >
      <SelectTrigger id={id} className="w-full">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {(allowNone || !value) && <SelectItem value={NONE}>{noneLabel}</SelectItem>}
        {options.map((option) => (
          <SelectItem key={option} value={option}>
            {labels[option] ?? option}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

type Precision = keyof typeof PRECISION_LABELS

/** A date with how precisely it is known (`exact` ... `year`). */
export function DateWithPrecision({ id, label, at, precision, onChange, disabled }: {
  id: string
  label: string
  at: string | null | undefined
  precision: Precision | null | undefined
  onChange: (at: string | null, precision: Precision) => void
  disabled?: boolean
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_9rem]">
      <fieldset disabled={disabled} className="min-w-0">
        <OptionalDateInput
          id={id}
          label={label}
          value={isoToDateOnly(at)}
          onChange={(value) => {
            const iso = dateOnlyToIso(value)
            onChange(iso, iso ? (precision && precision !== 'unknown' ? precision : 'day') : 'unknown')
          }}
        />
      </fieldset>
      <Field label="Known to the" htmlFor={`${id}-precision`}>
        <VocabSelect
          id={`${id}-precision`}
          labels={PRECISION_LABELS}
          value={(precision ?? 'unknown') as Precision}
          onChange={(value) => onChange(at ?? null, (value ?? 'unknown') as Precision)}
          disabled={disabled || !at}
        />
      </Field>
    </div>
  )
}

/** A DGNB Building Resource Passport class with a note (section 2.11). */
export function CircularityClassField({ id, label, hint, value, onChange, disabled }: {
  id: string
  label: string
  hint?: string
  value: CircularityClass | null | undefined
  onChange: (value: CircularityClass | null) => void
  disabled?: boolean
}) {
  return (
    <div className="space-y-2">
      <Field label={label} htmlFor={id} hint={hint}>
        <VocabSelect
          id={id}
          labels={DGNB_CLASS_LABELS}
          value={value?.class as DgnbClass | undefined}
          onChange={(next) => onChange(next ? { ...(value ?? {}), class: next } : null)}
          allowNone
          noneLabel="Not assessed"
          disabled={disabled}
        />
      </Field>
      {value && (
        <Input
          aria-label={`${label}: note`}
          value={value.note ?? ''}
          onChange={(event) => onChange({ ...value, note: event.target.value })}
          placeholder="Why this class (optional)"
          disabled={disabled}
        />
      )}
    </div>
  )
}

/** The origin block: kind, date, place, and for a deinstalled or demolished
 * piece the works it left, its position and connections (I16). */
export function OriginFields({ idPrefix, value, onChange, disabled }: {
  idPrefix: string
  value: Origin
  onChange: (value: Origin) => void
  disabled?: boolean
}) {
  const set = (patch: Partial<Origin>) => onChange({ ...value, ...patch })
  const work = value.construction_work ?? ({ name: '' } as ConstructionWork)
  const setWork = (patch: Partial<ConstructionWork>) =>
    set({ construction_work: { ...work, ...patch } })
  const works = WORKS_ORIGIN_KINDS.includes(value.kind)
  const connections = value.connection_types ?? []

  return (
    <fieldset disabled={disabled} className="space-y-3">
      <Field label="How it entered circulation" htmlFor={`${idPrefix}-kind`}>
        <VocabSelect
          id={`${idPrefix}-kind`}
          labels={ORIGIN_KIND_LABELS}
          value={value.kind}
          onChange={(kind) => set({
            kind: kind ?? 'unknown',
            ...(WORKS_ORIGIN_KINDS.includes(kind ?? 'unknown') ? {} : { planned: false }),
          })}
          disabled={disabled}
        />
      </Field>
      {works && (
        <div className="flex items-start gap-2">
          <Checkbox
            id={`${idPrefix}-planned`}
            checked={value.planned === true}
            onCheckedChange={(checked) => set({ planned: checked === true })}
          />
          <div className="space-y-0.5">
            <Label htmlFor={`${idPrefix}-planned`}>Planned</Label>
            <p className="text-xs text-muted-foreground">
              Still in place: identified in its works, not yet deinstalled. The date is then the planned
              one, or empty. Record the deinstallation on the component page later.
            </p>
          </div>
        </div>
      )}
      <DateWithPrecision
        id={`${idPrefix}-at`}
        label={value.planned ? 'Planned deinstallation on (optional)' : 'Left its previous context on'}
        at={value.at}
        precision={value.at_precision}
        onChange={(at, at_precision) => set({ at, at_precision })}
        disabled={disabled}
      />
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Place" htmlFor={`${idPrefix}-place`}>
          <Input
            id={`${idPrefix}-place`}
            value={value.place?.name ?? ''}
            onChange={(event) => set({ place: { ...(value.place ?? {}), name: event.target.value } })}
            placeholder="Site or yard"
          />
        </Field>
        <Field label="Address" htmlFor={`${idPrefix}-address`}>
          <Input
            id={`${idPrefix}-address`}
            value={value.place?.address ?? ''}
            onChange={(event) => set({ place: { ...(value.place ?? {}), address: event.target.value } })}
          />
        </Field>
      </div>

      {works && (
        <div className="space-y-3 rounded-md border border-border/70 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            The works it left
          </p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Construction work" htmlFor={`${idPrefix}-work`}>
              <Input
                id={`${idPrefix}-work`}
                value={work.name ?? ''}
                onChange={(event) => setWork({ name: event.target.value })}
                placeholder="Building or structure"
              />
            </Field>
            <Field label="Identifier" htmlFor={`${idPrefix}-work-id`}>
              <Input
                id={`${idPrefix}-work-id`}
                value={work.identifier ?? ''}
                onChange={(event) => setWork({ identifier: event.target.value })}
                placeholder="e.g. cadastral or project number"
              />
            </Field>
            <Field label="Year built" htmlFor={`${idPrefix}-work-year`}>
              <Input
                id={`${idPrefix}-work-year`}
                inputMode="numeric"
                value={work.year_built ?? ''}
                onChange={(event) => {
                  const year = parseInt(event.target.value, 10)
                  setWork({ year_built: Number.isFinite(year) ? year : null })
                }}
              />
            </Field>
            <Field label="Construction method" htmlFor={`${idPrefix}-work-method`}>
              <VocabSelect
                id={`${idPrefix}-work-method`}
                labels={CONSTRUCTION_METHOD_LABELS}
                value={work.construction_method as ConstructionMethod | null | undefined}
                onChange={(construction_method) => setWork({ construction_method })}
                allowNone
                disabled={disabled}
              />
            </Field>
          </div>
          <Field label="Position in the works" htmlFor={`${idPrefix}-position`}>
            <Input
              id={`${idPrefix}-position`}
              value={value.position_in_work ?? ''}
              onChange={(event) => set({ position_in_work: event.target.value })}
              placeholder="e.g. 2nd floor, axis C/4, inner wall"
            />
          </Field>
          <Field label="Connections" hint="How it was joined to the works (DGNB connection types).">
            <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 sm:grid-cols-4">
              {(Object.keys(CONNECTION_TYPE_LABELS) as ConnectionType[]).map((type) => (
                <label key={type} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={connections.includes(type)}
                    onCheckedChange={(checked) =>
                      set({
                        connection_types: checked
                          ? [...connections, type]
                          : connections.filter((c) => c !== type),
                      })
                    }
                  />
                  {CONNECTION_TYPE_LABELS[type]}
                </label>
              ))}
            </div>
          </Field>
          <CircularityClassField
            id={`${idPrefix}-detachability`}
            label="Detachability"
            hint="DGNB class of how well it came apart from the works."
            value={value.detachability}
            onChange={(detachability) => set({ detachability })}
            disabled={disabled}
          />
        </div>
      )}

      <Field label="Method" htmlFor={`${idPrefix}-method`}>
        <Input
          id={`${idPrefix}-method`}
          value={value.method ?? ''}
          onChange={(event) => set({ method: event.target.value })}
          placeholder="e.g. saw cut, crane lift"
        />
      </Field>
      <Field label="Notes" htmlFor={`${idPrefix}-notes`}>
        <Textarea
          id={`${idPrefix}-notes`}
          rows={2}
          value={value.notes ?? ''}
          onChange={(event) => set({ notes: event.target.value })}
        />
      </Field>
    </fieldset>
  )
}
