/**
 * What is missing or wrong in the evidence form, by section (decision 8.134
 * a, e): the form's own checks (a required field left empty, a number that is
 * none, a date that is none) and the server's problems after a save, both as
 * `Issue`s that name their section and the field to jump to. The server stays
 * the authority: these checks only say early what it would say anyway.
 *
 * Run: npm test
 */
import type { FormState } from '@/components/evidence/form/state'
import { finalMessage, type DatePrecision } from '@/lib/dateField'
import type { JsonSchema, MethodInfo, ProblemRow } from '@/lib/evidence/api'
import { layoutOf } from '@/lib/evidence/layout'
import {
  isBlank,
  isObject,
  kindOf,
  labelOf,
  parseNumber,
  resolve,
  type FormObject,
} from '@/lib/evidence/schema'

export type SectionId = 'method' | 'who' | 'what' | 'files' | 'notes'

export const SECTION_ORDER: SectionId[] = ['method', 'who', 'what', 'files', 'notes']

export type SectionState = 'done' | 'missing' | 'error' | 'optional'

export type Issue = {
  section: SectionId
  message: string
  /** The DOM id of the field to jump to. */
  target?: string
  /** The record (test area, finding, bar group) a field belongs to, 0-based. */
  record?: number
  source: 'form' | 'server'
}

export type FieldIssue = { path: string[]; message: string; target: string }

const FLEX: DatePrecision[] = ['year', 'month', 'day']

/**
 * The required fields a payload leaves empty, the numbers that are none and
 * the dates that are none. `idPrefix` makes the DOM ids `SchemaFields`
 * gives the fields (`<prefix>-<dotted path with dashes>`); an issue inside a
 * list item points at the list.
 */
export function payloadIssues(
  schema: JsonSchema,
  root: JsonSchema,
  value: FormObject,
  idPrefix: string,
  options: { hide?: string[]; dateFields?: string[]; flexDateFields?: string[] } = {},
  path: string[] = [],
  listTarget?: string,
): FieldIssue[] {
  const out: FieldIssue[] = []
  const required = new Set(schema.required ?? [])
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    const here = [...path, key]
    const dotted = here.join('.')
    if (options.hide?.some((h) => dotted === h || dotted.startsWith(`${h}.`))) continue
    const resolved = resolve(prop, root)
    if (prop.server_computed || resolved.schema.server_computed) continue
    const label = labelOf(key, resolved)
    const raw = value[key]
    const mandatory = required.has(key)
    const target = listTarget ?? `${idPrefix}-${dotted.replace(/\./g, '-')}`
    const kind = kindOf(resolved, root)

    if (kind === 'object') {
      if (isObject(raw)) {
        if (mandatory || !isBlank(raw)) {
          out.push(...payloadIssues(resolved.schema, root, raw as FormObject, idPrefix, options, here, listTarget))
        }
      } else if (mandatory) {
        out.push({ path: here, message: `${label} is missing.`, target })
      }
      continue
    }
    if (kind === 'boolean') continue
    if (kind === 'list') {
      const items = Array.isArray(raw) ? raw : []
      if (mandatory && items.length === 0) out.push({ path: here, message: `${label}: add at least one.`, target })
      const itemSchema = resolve(resolved.schema.items ?? {}, root)
      items.forEach((item, index) => {
        if (!isObject(item)) return
        for (const inner of payloadIssues(itemSchema.schema, root, item as FormObject, idPrefix, options, [...here, String(index)], target)) {
          out.push({ ...inner, message: `${label} ${index + 1}: ${inner.message}` })
        }
      })
      continue
    }

    const blank = isBlank(raw)
    if (blank) {
      if (mandatory) out.push({ path: here, message: `${label} is missing.`, target })
      continue
    }
    if (kind === 'number' || kind === 'integer') {
      if (parseNumber(String(raw)) === null) out.push({ path: here, message: `${label} is not a number.`, target })
    } else if (kind === 'numbers' || kind === 'points' || kind === 'vec3') {
      const min = resolved.schema.minItems
      const count = Array.isArray(raw) ? raw.filter((v) => !isBlank(v)).length : 0
      if (min && count < min) out.push({ path: here, message: `${label}: at least ${min} needed.`, target })
    } else if (typeof raw === 'string') {
      if (options.dateFields?.includes(dotted)) {
        const message = finalMessage(raw, ['day'])
        if (message) out.push({ path: here, message: `${label}: ${message}`, target })
      } else if (options.flexDateFields?.includes(dotted)) {
        const message = finalMessage(raw, FLEX)
        if (message) out.push({ path: here, message: `${label}: ${message}`, target })
      }
    }
  }
  return out
}

/** A bar of a reinforcement layout, as the form holds it. */
export function barIssues(bar: FormObject): string[] {
  const out: string[] = []
  const diameter = parseNumber(String(bar.diameter_mm ?? ''))
  if (isBlank(bar.diameter_mm)) out.push('Diameter is missing.')
  else if (diameter === null || diameter <= 0) out.push('Diameter must be a number above zero.')
  const cover = String(bar.cover_mm ?? '')
  if (cover.trim() !== '' && (parseNumber(cover) === null || (parseNumber(cover) ?? 0) < 0)) {
    out.push('Cover must be a number, zero or more.')
  }
  const points = Array.isArray(bar.points) ? bar.points : []
  const valid = points.filter((p) => Array.isArray(p) && p.length === 3 && p.every((v) => parseNumber(String(v)) !== null))
  if (points.length - valid.length > 0) out.push('Each point needs three numbers: x y z.')
  else if (valid.length < 2) out.push('A bar needs at least two points.')
  return out
}

/** The key facts of a record that decide whether it can be saved (client side). */
export function formIssues(state: FormState, method: MethodInfo): Issue[] {
  const layout = layoutOf(method.name)
  const issues: Issue[] = []
  const schema = method.payload_schema
  const options = {
    dateFields: layout.dateFields, flexDateFields: layout.flexDateFields,
  }

  if (method.context_time !== 'sampled_at') {
    const message = state.observedAt.trim() === ''
      ? 'The date of the observation is missing.'
      : finalMessage(state.observedAt, ['day'])
    if (message) issues.push({ section: 'who', message, target: 'observed-at', source: 'form' })
  }

  const recordName = layout.recordLabel.charAt(0).toUpperCase() + layout.recordLabel.slice(1)
  if (layout.fanOut === 'areas') {
    state.records.forEach((record, index) => {
      const merged: FormObject = { ...record.payload }
      for (const key of layout.shared) merged[key] = state.shared[key]
      for (const issue of payloadIssues(schema, schema, merged, `record-r${index}`, options)) {
        // a shared field is shown once, above the records
        const shared = layout.shared.some((s) => issue.path[0] === s)
        if (shared && index > 0) continue          // the shared settings are named once
        issues.push({
          section: 'what',
          message: shared ? issue.message : `${recordName} ${index + 1}: ${issue.message}`,
          target: shared ? issue.target.replace(`record-r${index}`, 'record-shared') : issue.target,
          record: shared ? undefined : index,
          source: 'form',
        })
      }
      if (method.position_required && !record.position.description.trim() && record.position.kind === 'none') {
        issues.push({
          section: 'what', message: `${recordName} ${index + 1}: say where on the element.`,
          target: `record-r${index}-position`, record: index, source: 'form',
        })
      }
    })
  } else if (layout.fanOut === 'observations') {
    state.observations.forEach((o, index) => {
      if (!o.quantity) {
        issues.push({ section: 'what', message: `Finding ${index + 1}: say what was observed.`, record: index, source: 'form' })
      }
      if (o.quantity && o.value.trim() === '') {
        issues.push({ section: 'what', message: `Finding ${index + 1}: the severity or width is missing.`, record: index, source: 'form' })
      } else if (o.value.trim() !== '' && parseNumber(o.value) === null) {
        issues.push({ section: 'what', message: `Finding ${index + 1}: the value is not a number.`, record: index, source: 'form' })
      }
    })
    if (state.observations.length === 0) {
      issues.push({ section: 'what', message: 'Add at least one finding.', source: 'form' })
    }
  } else {
    const payload = state.records[0]?.payload ?? {}
    for (const issue of payloadIssues(schema, schema, payload, 'claim', { ...options, hide: layout.fanOut === 'single' ? ['bars'] : [] })) {
      issues.push({ section: 'what', message: issue.message, target: issue.target, source: 'form' })
    }
    if (layout.fanOut === 'single') {
      const bars = Array.isArray(payload.bars) ? (payload.bars as FormObject[]) : []
      if (bars.length === 0) issues.push({ section: 'what', message: 'Add at least one bar.', target: 'claim-bars', source: 'form' })
      bars.forEach((bar, index) => {
        for (const message of barIssues(isObject(bar) ? (bar as FormObject) : {})) {
          issues.push({
            section: 'what', message: `Bar ${index + 1}: ${message}`, target: 'claim-bars', record: index, source: 'form',
          })
        }
      })
    }
    if (layout.fanOut === 'pieces') {
      if (!method.summary_optional && !state.summary.quantity) {
        issues.push({ section: 'what', message: 'Say which property the claim is about.', target: 'summary-quantity', source: 'form' })
      }
      if (state.pieces.length === 0) {
        issues.push({ section: 'what', message: 'Name at least one element.', source: 'form' })
      }
    }
  }
  return issues
}

/** The section a problem path of the server belongs to. */
export function sectionOfPath(path: string): SectionId {
  if (path === 'observed_at' || path.startsWith('observed_at') || path.startsWith('standard')
    || path.startsWith('performed_by') || path.startsWith('sampled_at')) return 'who'
  if (path.startsWith('attachments') || path.startsWith('files')) return 'files'
  if (path === 'notes') return 'notes'
  return 'what'
}

/** The DOM id of the field a problem of the server names. */
export function targetOfPath(path: string, method: MethodInfo, record: number | undefined): string | undefined {
  const layout = layoutOf(method.name)
  if (path.startsWith('observed_at')) return 'observed-at'
  if (path.startsWith('standard')) return 'standard-code'
  if (path.startsWith('summary')) return 'summary-quantity'
  if (path === 'notes') return 'notes'
  if (path.startsWith('payload.')) {
    const rest = path.slice('payload.'.length).replace(/\./g, '-')
    if (layout.fanOut === 'areas') {
      const key = layout.shared.some((s) => path.slice(8) === s || path.slice(8).startsWith(`${s}.`))
        ? 'record-shared' : `record-r${record ?? 0}`
      return `${key}-${rest.replace(/-\d+(?=-|$)/g, '')}`
    }
    if (layout.fanOut === 'single' && rest.startsWith('bars')) return 'claim-bars'
    return layout.fanOut === 'pieces' || layout.fanOut === 'single' ? `claim-${rest}` : undefined
  }
  if (path.startsWith('position')) return layout.fanOut === 'areas' ? `record-r${record ?? 0}-position` : 'layout-position'
  return undefined
}

export function serverIssues(rows: ProblemRow[], method: MethodInfo): Issue[] {
  return rows.map((row) => ({
    section: sectionOfPath(row.path),
    message: row.message,
    target: targetOfPath(row.path, method, row.record),
    record: row.record,
    source: 'server' as const,
  }))
}

export type StateContext = {
  hasMethod: boolean
  files: number
  notes: string
  /** Attachments a correction carries over, still there. */
  carried?: number
}

/** done / missing / error / optional per section. */
export function sectionStates(issues: Issue[], ctx: StateContext): Record<SectionId, SectionState> {
  const of = (section: SectionId): SectionState => {
    const own = issues.filter((i) => i.section === section)
    if (own.some((i) => i.source === 'server')) return 'error'
    if (own.length > 0) return 'missing'
    return 'done'
  }
  return {
    method: ctx.hasMethod ? 'done' : 'missing',
    who: of('who'),
    what: ctx.hasMethod ? of('what') : 'missing',
    files: of('files') !== 'done' ? of('files') : ctx.files + (ctx.carried ?? 0) > 0 ? 'done' : 'optional',
    notes: of('notes') !== 'done' ? of('notes') : ctx.notes.trim() ? 'done' : 'optional',
  }
}

export function issuesOf(issues: Issue[], section: SectionId): Issue[] {
  return issues.filter((i) => i.section === section)
}
