/**
 * The document of a published reinforcement layout, filled once (RL5,
 * decision 8.142 b): which of its fields are empty and the body of the
 * `PATCH /evidence/{id}` that sets them. A set field changes only through a
 * correction, so only the empty ones are offered.
 *
 * Run: npm test
 */
import { finalMessage } from '@/lib/dateField'

export const DOCUMENT_FIELDS = ['title', 'date', 'reference', 'url', 'retrieved_at'] as const
export type DocumentField = (typeof DOCUMENT_FIELDS)[number]

export const DOCUMENT_LABELS: Record<DocumentField, string> = {
  title: 'Title of the drawing',
  date: 'Date of the drawing',
  reference: 'Reference',
  url: 'Link to the drawing online',
  retrieved_at: 'The day the link was read',
}

export type DocumentValues = Record<DocumentField, string>

const text = (value: unknown): string => (typeof value === 'string' ? value.trim() : '')

/** The document of a layout payload with every field as text (empty when not set). */
export function documentValues(payload: unknown): DocumentValues {
  const document = (payload as { document?: Record<string, unknown> | null } | null | undefined)?.document ?? {}
  return Object.fromEntries(DOCUMENT_FIELDS.map((key) => [key, text(document?.[key])])) as DocumentValues
}

/** The fields still empty: what a moderator may fill in once. */
export function emptyDocumentFields(payload: unknown): DocumentField[] {
  const values = documentValues(payload)
  return DOCUMENT_FIELDS.filter((key) => values[key] === '')
}

/** Whether the document has no title yet: then a title is needed before anything else can be set. */
export function needsTitle(payload: unknown): boolean {
  return documentValues(payload).title === ''
}

/** What is wrong with the values typed for the empty fields, by field. */
export function fillProblems(payload: unknown, typed: Partial<DocumentValues>): Partial<Record<DocumentField, string>> {
  const problems: Partial<Record<DocumentField, string>> = {}
  const empty = emptyDocumentFields(payload)
  const any = empty.some((key) => text(typed[key]) !== '')
  if (needsTitle(payload) && any && text(typed.title) === '') {
    problems.title = 'A title is needed for the document.'
  }
  const url = text(typed.url)
  if (empty.includes('url') && url !== '') {
    try {
      const parsed = new URL(url)
      if ((parsed.protocol !== 'http:' && parsed.protocol !== 'https:') || !parsed.hostname) throw new Error('scheme')
      if (/\s/.test(url) || url.length > 2048) throw new Error('shape')
    } catch {
      problems.url = 'A link starts with http:// or https:// and has a host, without spaces.'
    }
  }
  if (empty.includes('date') && text(typed.date) !== '') {
    const message = finalMessage(text(typed.date), ['year', 'month', 'day'])
    if (message) problems.date = message
  }
  if (empty.includes('retrieved_at') && text(typed.retrieved_at) !== '') {
    const message = finalMessage(text(typed.retrieved_at), ['day'])
    if (message) problems.retrieved_at = message
  }
  return problems
}

/** The PATCH body: the typed values of the empty fields only, nothing else of the payload. */
export function fillBody(payload: unknown, typed: Partial<DocumentValues>): { payload: { document: Record<string, string> } } {
  const document: Record<string, string> = {}
  for (const key of emptyDocumentFields(payload)) {
    const value = text(typed[key])
    if (value !== '') document[key] = value
  }
  return { payload: { document } }
}
