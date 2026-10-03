'use client'

/**
 * Renders the fields of a payload JSON Schema (decision 7.1): the form is
 * generated from `GET /evidence/methods`, so a new method or field needs no
 * frontend change except an entry in `lib/evidence/layout.ts`. Labels and
 * "?" texts are the schema's. Server-computed fields are not entered: they
 * are named once under the fields ("the server computes ...").
 */
import { useEffect, useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'

import { Field, NativeSelect, NumberList } from '@/components/evidence/controls'
import Help from '@/components/evidence/Help'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { JsonSchema } from '@/lib/evidence/api'
import type { MethodLayout } from '@/lib/evidence/layout'
import {
  emptyObject,
  emptyValue,
  kindOf,
  labelOf,
  resolve,
  type FormObject,
  type FormValue,
  type Resolved,
} from '@/lib/evidence/schema'
import { isObject } from '@/lib/evidence/schema'

export type OverrideContext = {
  path: string[]
  id: string
  parent: FormObject
  setParent: (next: FormObject) => void
  resolved: Resolved
  label: string
  required: boolean
  errors: string[]
}
export type Override = (ctx: OverrideContext) => React.ReactNode

export type SchemaFieldsProps = {
  schema: JsonSchema
  root: JsonSchema
  value: FormObject
  onChange: (next: FormObject) => void
  idPrefix: string
  layout: MethodLayout
  /** Problems of the server by payload path (`test_area.surface_preparation`). */
  errors?: Record<string, string[]>
  overrides?: Record<string, Override>
  /** Dotted paths (and their children) that are not shown here. */
  hide?: string[]
  /** Only these top-level keys. */
  only?: string[]
  path?: string[]
}

const dot = (path: string[]) => path.join('.')

function errorsAt(errors: Record<string, string[]> | undefined, path: string[]): string[] {
  if (!errors) return []
  const here = dot(path)
  return Object.entries(errors)
    .filter(([key]) => key === here || key.startsWith(`${here}.`))
    .flatMap(([, messages]) => messages)
}

export default function SchemaFields(props: SchemaFieldsProps) {
  const { schema, root, value, onChange, idPrefix, layout, errors, overrides, hide, only } = props
  const path = props.path ?? []
  const required = new Set(schema.required ?? [])
  const computed: { key: string; label: string; help: string }[] = []

  const setKey = (key: string, next: FormValue) => onChange({ ...value, [key]: next })

  const rows: React.ReactNode[] = []
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    if (only && path.length === 0 && !only.includes(key)) continue
    const here = [...path, key]
    const dotted = dot(here)
    if (hide?.some((h) => dotted === h || dotted.startsWith(`${h}.`))) continue
    const resolved = resolve(prop, root)
    const label = labelOf(key, resolved)
    if (prop.server_computed || resolved.schema.server_computed) {
      computed.push({ key: dotted, label, help: resolved.description })
      continue
    }
    const id = `${idPrefix}-${dotted.replace(/\./g, '-')}`
    const isRequired = required.has(key)
    const fieldErrors = errorsAt(errors, here)
    const override = overrides?.[dotted]
    if (override) {
      rows.push(
        <div key={key}>
          {override({
            path: here, id, parent: value, setParent: onChange, resolved, label,
            required: isRequired, errors: fieldErrors,
          })}
        </div>,
      )
      continue
    }
    const kind = kindOf(resolved, root)
    const current = value[key]
    const common = { id, label, help: resolved.description, required: isRequired, errors: fieldErrors }

    if (kind === 'object') {
      const object = isObject(current) ? (current as FormObject) : null
      if (object === null) {
        rows.push(
          <div key={key} className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setKey(key, emptyObject(resolved.schema, root))}
            >
              <Plus className="mr-1 h-3.5 w-3.5" />{label}
            </Button>
            <Help text={resolved.description} label={label} />
          </div>,
        )
      } else {
        rows.push(
          <fieldset key={key} className="space-y-3 rounded-md border border-border/70 p-3">
            <legend className="flex items-center gap-1 px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {label}
              <Help text={resolved.description} label={label} />
            </legend>
            <SchemaFields
              {...props}
              schema={resolved.schema}
              value={object}
              onChange={(next) => setKey(key, next)}
              path={here}
              only={undefined}
            />
            {resolved.nullable && !isRequired && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-muted-foreground"
                onClick={() => setKey(key, null)}
              >
                <Trash2 className="mr-1 h-3 w-3" />Remove {label.toLowerCase()}
              </Button>
            )}
          </fieldset>,
        )
      }
      continue
    }

    if (kind === 'boolean') {
      rows.push(
        <div key={key} className="flex items-start gap-2">
          <Checkbox
            id={id}
            checked={current === true}
            onCheckedChange={(checked) => setKey(key, checked === true)}
            className="mt-0.5"
          />
          <div className="flex items-center gap-1">
            <Label htmlFor={id} className="text-sm font-normal">{label}</Label>
            <Help text={resolved.description} label={label} />
          </div>
        </div>,
      )
      continue
    }

    if (kind === 'enum') {
      const options = (resolved.schema.enum ?? []).map((v) => ({ value: String(v), label: enumLabel(String(v)) }))
      rows.push(
        <Field key={key} {...common}>
          {options.length <= 4 ? (
            <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
              {options.map((option) => {
                const active = current === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setKey(key, active && !isRequired ? '' : option.value)}
                    className={`rounded-md border px-2.5 py-1.5 text-sm ${
                      active
                        ? 'border-primary bg-primary/10 font-medium'
                        : 'border-border hover:bg-muted/50'
                    }`}
                  >
                    {option.label}
                  </button>
                )
              })}
            </div>
          ) : (
            <NativeSelect
              id={id}
              value={typeof current === 'string' ? current : ''}
              onChange={(next) => setKey(key, next)}
              options={options}
            />
          )}
        </Field>,
      )
      continue
    }

    if (kind === 'numbers') {
      rows.push(
        <Field key={key} {...common}>
          <NumberList
            id={id}
            values={Array.isArray(current) ? (current as string[]) : []}
            onChange={(next) => setKey(key, next)}
          />
        </Field>,
      )
      continue
    }

    if (kind === 'vec3') {
      const parts = Array.isArray(current) ? (current as string[]) : ['', '', '']
      rows.push(
        <Field key={key} {...common}>
          <div className="grid grid-cols-3 gap-2">
            {['x', 'y', 'z'].map((axis, i) => (
              <Input
                key={axis}
                id={i === 0 ? id : undefined}
                aria-label={`${label} ${axis}`}
                inputMode="decimal"
                placeholder={axis}
                value={parts[i] ?? ''}
                onChange={(event) => {
                  const next = [...parts]
                  while (next.length < 3) next.push('')
                  next[i] = event.target.value
                  setKey(key, next)
                }}
              />
            ))}
          </div>
        </Field>,
      )
      continue
    }

    if (kind === 'points') {
      rows.push(
        <Field key={key} {...common}>
          <PointsField
            id={id}
            value={Array.isArray(current) ? (current as string[][]) : []}
            onChange={(next) => setKey(key, next)}
          />
        </Field>,
      )
      continue
    }

    if (kind === 'list' && resolve(resolved.schema.items ?? {}, root).schema.type === 'string') {
      rows.push(
        <Field key={key} {...common}>
          <StringListField
            id={id}
            value={Array.isArray(current) ? (current as string[]) : []}
            onChange={(next) => setKey(key, next)}
          />
        </Field>,
      )
      continue
    }

    if (kind === 'list') {
      const itemSchema = resolve(resolved.schema.items ?? {}, root)
      const items = Array.isArray(current) ? current : []
      rows.push(
        <fieldset key={key} className="space-y-2 rounded-md border border-border/70 p-3">
          <legend className="flex items-center gap-1 px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {label}
            <Help text={resolved.description} label={label} />
          </legend>
          {fieldErrors.length > 0 && (
            <ul role="alert">
              {fieldErrors.map((m) => <li key={m} className="text-xs text-destructive">{m}</li>)}
            </ul>
          )}
          {items.map((item, index) => (
            <div key={index} className="space-y-3 rounded-md border border-dashed border-border p-2">
              {isObject(item) ? (
                <SchemaFields
                  {...props}
                  schema={itemSchema.schema}
                  value={item as FormObject}
                  onChange={(next) => {
                    const copy = [...items]
                    copy[index] = next
                    setKey(key, copy)
                  }}
                  path={[...here, String(index)]}
                  idPrefix={`${id}-${index}`}
                  only={undefined}
                />
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 text-xs text-muted-foreground"
                onClick={() => setKey(key, items.filter((_, i) => i !== index))}
              >
                <Trash2 className="mr-1 h-3 w-3" />Remove
              </Button>
            </div>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => setKey(key, [...items, emptyValue(itemSchema, root, true)])}
          >
            <Plus className="mr-1 h-3.5 w-3.5" />Add {label.toLowerCase().replace(/s$/, '')}
          </Button>
        </fieldset>,
      )
      continue
    }

    // strings and numbers
    const numeric = kind === 'number' || kind === 'integer'
    const dateField = layout.dateFields.includes(dotted)
    const long = layout.longText.includes(dotted)
    rows.push(
      <Field key={key} {...common}>
        {long ? (
          <Textarea
            id={id}
            rows={2}
            value={typeof current === 'string' ? current : ''}
            onChange={(event) => setKey(key, event.target.value)}
          />
        ) : (
          <Input
            id={id}
            type={dateField ? 'date' : 'text'}
            inputMode={numeric ? (kind === 'integer' ? 'numeric' : 'decimal') : undefined}
            value={typeof current === 'string' ? current : ''}
            onChange={(event) => setKey(key, event.target.value)}
          />
        )}
      </Field>,
    )
  }

  return (
    <div className="space-y-3">
      {rows}
      {computed.length > 0 && (
        <p className="flex flex-wrap items-center gap-x-1 text-xs text-muted-foreground">
          The server computes:
          {computed.map((c, i) => (
            <span key={c.key} className="inline-flex items-center gap-0.5">
              {c.label.toLowerCase()}
              <Help text={c.help} label={c.label} />
              {i < computed.length - 1 ? ',' : '.'}
            </span>
          ))}
        </p>
      )}
    </div>
  )
}

/** "fixed_in_structure" -> "Fixed in structure"; "2:1" stays. */
export function enumLabel(value: string): string {
  // codes such as Q_N or 2:1 are shown as they are
  if (/[A-Z:]/.test(value)) return value
  if (!value.includes('_')) {
    return value.charAt(0).toUpperCase() + value.slice(1)
  }
  const text = value.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** One point per line, "x y z" (a bar's centreline, stored coordinates). */
function PointsField({
  id,
  value,
  onChange,
}: {
  id: string
  value: string[][]
  onChange: (next: string[][]) => void
}) {
  const asText = (points: string[][]) => points.map((p) => p.join(' ')).join('\n')
  const [text, setText] = useState(asText(value))
  useEffect(() => {
    // follow outside changes (a picked point), not our own typing
    const parsed = parse(text)
    if (JSON.stringify(parsed) !== JSON.stringify(value)) setText(asText(value))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return (
    <div className="space-y-1">
      <Textarea
        id={id}
        rows={4}
        className="font-mono text-xs"
        placeholder={'x y z (mm)\nx y z'}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          onChange(parse(event.target.value))
        }}
      />
      <p className="text-xs text-muted-foreground">
        One point per line in the stored coordinates of the snapshot, at least two.
      </p>
    </div>
  )
}

function parse(text: string): string[][] {
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.split(/[\s,;]+/).filter(Boolean))
}

/** A list of words typed separated by commas (e.g. the standards a laboratory covers). */
function StringListField({
  id,
  value,
  onChange,
}: {
  id: string
  value: string[]
  onChange: (next: string[]) => void
}) {
  const [text, setText] = useState(value.join(', '))
  useEffect(() => {
    const parsed = text.split(',').map((t) => t.trim()).filter(Boolean)
    if (JSON.stringify(parsed) !== JSON.stringify(value)) setText(value.join(', '))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])
  return (
    <Input
      id={id}
      value={text}
      placeholder="comma separated"
      onChange={(event) => {
        setText(event.target.value)
        onChange(event.target.value.split(',').map((t) => t.trim()).filter(Boolean))
      }}
    />
  )
}
