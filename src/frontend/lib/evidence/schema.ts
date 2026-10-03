/**
 * Helpers that read the payload JSON Schema the backend serves with
 * `GET /evidence/methods` (pydantic output): `$ref` / nullable unwrapping,
 * an empty form value per schema, and the conversion between form values
 * (numbers kept as strings while typing) and the payload JSON. The form is
 * generated from the schema; labels and help text are the schema's.
 */
import type { JsonSchema } from '@/lib/evidence/api'

/** What the form holds: numbers stay text until submit. */
export type FormValue = string | boolean | null | FormValue[] | { [key: string]: FormValue }
export type FormObject = { [key: string]: FormValue }

export type Resolved = {
  schema: JsonSchema
  nullable: boolean
  title: string
  description: string
}

export function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

/** Follow a local `$ref` (`#/$defs/Name`). */
export function deref(schema: JsonSchema, root: JsonSchema): JsonSchema {
  if (!schema.$ref) return schema
  const name = schema.$ref.split('/').pop() ?? ''
  const target = root.$defs?.[name]
  if (!target) return schema
  const { $ref: _ref, ...rest } = schema
  void _ref
  return { ...target, ...rest }
}

/**
 * The schema of a property with `$ref` followed and `anyOf [X, null]`
 * unwrapped; the property's own title and description win over the
 * target's.
 */
export function resolve(schema: JsonSchema, root: JsonSchema): Resolved {
  let nullable = false
  let current = deref(schema, root)
  const description = schema.description ?? current.description ?? ''
  if (current.anyOf) {
    const options = current.anyOf.map((s) => deref(s, root))
    nullable = options.some((s) => s.type === 'null')
    const rest = options.filter((s) => s.type !== 'null')
    // "integer | number" (a severity or a width) reads as number
    const numeric = rest.length > 1 && rest.every((s) => s.type === 'integer' || s.type === 'number')
    current = numeric ? { type: 'number' } : rest[0] ?? { type: 'string' }
  }
  return {
    schema: current,
    nullable,
    title: schema.title ?? current.title ?? '',
    description: description || current.description || '',
  }
}

export type FieldKind =
  | 'object'
  | 'enum'
  | 'boolean'
  | 'integer'
  | 'number'
  | 'string'
  | 'numbers'
  | 'vec3'
  | 'points'
  | 'list'

export function kindOf(resolved: Resolved, root: JsonSchema): FieldKind {
  const { schema } = resolved
  if (schema.enum) return 'enum'
  switch (schema.type) {
    case 'object':
      return 'object'
    case 'boolean':
      return 'boolean'
    case 'integer':
      return 'integer'
    case 'number':
      return 'number'
    case 'array': {
      const item = resolve(schema.items ?? {}, root).schema
      if (item.type === 'number' || item.type === 'integer') {
        return schema.minItems === 3 && schema.maxItems === 3 ? 'vec3' : 'numbers'
      }
      if (item.type === 'array') return 'points'
      return 'list'
    }
    default:
      return 'string'
  }
}

const UNIT_WORDS: Record<string, string> = {
  mm: 'mm', nm: 'Nm', c: 'deg C', kn: 'kN', mpa: 'MPa', g: 'g', kg: 'kg', m3: 'm3', mm2: 'mm2',
  deg: 'deg', ld: 'l/d',
}

/** "Min Spacing Mm" --> "Min spacing mm": sentence case, units as written. */
export function labelOf(key: string, resolved: Resolved): string {
  const source = resolved.title || key.replace(/_/g, ' ')
  const words = source.split(/\s+/).filter(Boolean)
  return words
    .map((word, i) => {
      const unit = UNIT_WORDS[word.toLowerCase()]
      if (unit !== undefined && i > 0) return unit
      if (word.length <= 3 && word === word.toUpperCase() && /[A-Z]/.test(word)) return word // N, Q, R, NR
      return i === 0 ? word.charAt(0).toUpperCase() + word.slice(1).toLowerCase() : word.toLowerCase()
    })
    .join(' ')
}

/** An empty form value for a schema (what a fresh record starts as). */
export function emptyValue(resolved: Resolved, root: JsonSchema, required: boolean): FormValue {
  const { schema } = resolved
  switch (kindOf(resolved, root)) {
    case 'object': {
      if (resolved.nullable && !required) return null
      return emptyObject(schema, root)
    }
    case 'boolean':
      return schema.default === true
    case 'numbers':
    case 'points':
    case 'list':
      return []
    case 'vec3':
      return ['', '', '']
    case 'enum':
      return required || schema.default === undefined || schema.default === null
        ? ''
        : String(schema.default)
    default:
      return schema.default === undefined || schema.default === null ? '' : String(schema.default)
  }
}

export function emptyObject(schema: JsonSchema, root: JsonSchema): FormObject {
  const required = new Set(schema.required ?? [])
  const out: FormObject = {}
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    const resolved = resolve(prop, root)
    if (resolved.schema.server_computed || prop.server_computed) continue
    out[key] = emptyValue(resolved, root, required.has(key))
  }
  return out
}

const NUMBER = /^\s*-?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?\s*$/

export function parseNumber(text: string): number | null {
  if (!NUMBER.test(text)) return null
  const value = Number(text.trim().replace(',', '.'))
  return Number.isFinite(value) ? value : null
}

/** True when nothing was entered (so an optional block is left out). */
export function isBlank(value: FormValue | undefined): boolean {
  if (value === undefined || value === null) return true
  if (typeof value === 'string') return value.trim() === ''
  if (typeof value === 'boolean') return false
  if (Array.isArray(value)) return value.every((v) => isBlank(v))
  return Object.values(value).every((v) => isBlank(v))
}

/**
 * The payload JSON for a form object. Blank optional values are left out,
 * the server-computed fields are never sent, numbers are parsed (a text
 * that is not a number is kept as text so the server names the field).
 */
export function toPayload(
  schema: JsonSchema,
  value: FormObject,
  root: JsonSchema,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  const required = new Set(schema.required ?? [])
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    const resolved = resolve(prop, root)
    if (resolved.schema.server_computed || prop.server_computed) continue
    const raw = value[key]
    const isRequired = required.has(key)
    const converted = convertValue(resolved, raw, root, isRequired)
    if (converted !== undefined) out[key] = converted
  }
  return out
}

function convertValue(
  resolved: Resolved,
  raw: FormValue | undefined,
  root: JsonSchema,
  required: boolean,
): unknown {
  const kind = kindOf(resolved, root)
  if (kind === 'boolean') {
    if (raw === undefined || raw === null) return undefined
    return raw === true || raw === 'true'
  }
  if (raw === undefined || raw === null) return undefined
  switch (kind) {
    case 'object': {
      if (!isObject(raw)) return undefined
      if (!required && isBlank(raw)) return undefined
      return toPayload(resolved.schema, raw as FormObject, root)
    }
    case 'integer':
    case 'number': {
      const text = String(raw)
      if (text.trim() === '') return undefined
      const parsed = parseNumber(text)
      return parsed === null ? text : parsed
    }
    case 'numbers': {
      if (!Array.isArray(raw)) return undefined
      const numbers = raw.map((v) => {
        const parsed = parseNumber(String(v))
        return parsed === null ? String(v) : parsed
      })
      return numbers.length === 0 && !required ? undefined : numbers
    }
    case 'vec3': {
      if (!Array.isArray(raw) || raw.every((v) => isBlank(v))) return undefined
      return raw.map((v) => {
        const parsed = parseNumber(String(v))
        return parsed === null ? String(v) : parsed
      })
    }
    case 'points': {
      if (!Array.isArray(raw)) return undefined
      return raw.map((point) =>
        (Array.isArray(point) ? point : []).map((v) => {
          const parsed = parseNumber(String(v))
          return parsed === null ? String(v) : parsed
        }),
      )
    }
    case 'list': {
      if (!Array.isArray(raw)) return undefined
      const itemSchema = resolve(resolved.schema.items ?? {}, root)
      const items = raw
        .map((item) => convertValue(itemSchema, item, root, true))
        .filter((v) => v !== undefined)
      return items.length === 0 && !required ? undefined : items
    }
    case 'enum': {
      const text = String(raw)
      return text === '' ? undefined : text
    }
    default: {
      const text = String(raw)
      if (text.trim() === '') return undefined
      return text
    }
  }
}

/** A stored payload as form values (repeat from my last record, edit a draft). */
export function fromPayload(
  schema: JsonSchema,
  payload: Record<string, unknown> | null | undefined,
  root: JsonSchema,
): FormObject {
  const base = emptyObject(schema, root)
  if (!payload) return base
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    const resolved = resolve(prop, root)
    if (resolved.schema.server_computed || prop.server_computed) continue
    const raw = payload[key]
    if (raw === undefined || raw === null) continue
    base[key] = formFrom(resolved, raw, root)
  }
  return base
}

function formFrom(resolved: Resolved, raw: unknown, root: JsonSchema): FormValue {
  switch (kindOf(resolved, root)) {
    case 'object':
      return isObject(raw) ? fromPayload(resolved.schema, raw, root) : null
    case 'boolean':
      return raw === true
    case 'numbers':
    case 'vec3':
      return Array.isArray(raw) ? raw.map((v) => String(v)) : []
    case 'points':
      return Array.isArray(raw)
        ? raw.map((p) => (Array.isArray(p) ? p.map((v) => String(v)) : []))
        : []
    case 'list': {
      const itemSchema = resolve(resolved.schema.items ?? {}, root)
      return Array.isArray(raw) ? raw.map((item) => formFrom(itemSchema, item, root)) : []
    }
    default:
      return raw === null || raw === undefined ? '' : String(raw)
  }
}

/** Read a value at a dotted path of a form object (`test_area.grid`). */
export function getAt(value: FormValue | undefined, path: string[]): FormValue | undefined {
  let current: FormValue | undefined = value
  for (const key of path) {
    if (!isObject(current)) return undefined
    current = (current as FormObject)[key]
  }
  return current
}

/** A copy of `value` with the dotted path set (objects along it are created). */
export function setAt(value: FormObject, path: string[], next: FormValue): FormObject {
  if (path.length === 0) return value
  const [head, ...rest] = path
  if (rest.length === 0) return { ...value, [head]: next }
  const child = value[head]
  const base: FormObject = isObject(child) ? (child as FormObject) : {}
  return { ...value, [head]: setAt(base, rest, next) }
}
