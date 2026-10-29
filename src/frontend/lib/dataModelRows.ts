/**
 * The rows of an example record of the "Data Model" page: one per top-level
 * field of its JSON, and one per field of the payload, each with the comment
 * written for it.
 */
import type { ExampleRecord } from '@/lib/dataModelExamples'
import type { Para } from '@/lib/dataModelText'

export type ExampleRow = { field: string; value: string; comment: Para; nested: boolean }

const VALUE_LIMIT = 90

/** A value as one short line: text as it is, anything else as compact JSON, cut when long. */
export function valueText(value: unknown): string {
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  const line = text === undefined ? '' : text
  return line.length > VALUE_LIMIT ? `${line.slice(0, VALUE_LIMIT - 3)}...` : line
}

function commentOf(record: ExampleRecord, key: string): Para {
  const comment = record.comments[key]
  if (comment === undefined) return []
  return typeof comment === 'string' ? [comment] : comment
}

export function exampleRows(record: ExampleRecord): ExampleRow[] {
  const rows: ExampleRow[] = []
  for (const [field, value] of Object.entries(record.json)) {
    const isPayload = field === 'payload' && value !== null && typeof value === 'object'
    rows.push({ field, value: isPayload ? '(see the details below)' : valueText(value), comment: commentOf(record, field), nested: false })
    if (isPayload) {
      for (const [name, inner] of Object.entries(value as Record<string, unknown>)) {
        rows.push({ field: `payload.${name}`, value: valueText(inner), comment: commentOf(record, `payload.${name}`), nested: true })
      }
    }
  }
  return rows
}

/** The raw JSON of a record, as it is folded below its table. */
export function rawJson(record: ExampleRecord): string {
  return JSON.stringify(record.json, null, 2)
}
