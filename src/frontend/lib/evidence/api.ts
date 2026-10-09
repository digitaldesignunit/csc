/**
 * Evidence routes as the web uses them (spec section 7.2): the registry
 * (`GET /evidence/methods`, `/evidence/quantities`), bulk create, the
 * lifecycle verbs, verification and attachments. Everything the form shows
 * as help text or a choice comes from the registry responses, never from a
 * copy in the frontend (decision 7.1).
 */
import type {
  EvidenceBulkItem,
  EvidenceView,
  PendingEvidenceItem,
  PropertiesView,
} from '@/generated'
import { BackendError, backendJson } from '@/lib/backend'

export type JsonSchema = {
  type?: string | string[]
  title?: string
  description?: string
  enum?: unknown[]
  const?: unknown
  default?: unknown
  items?: JsonSchema
  properties?: Record<string, JsonSchema>
  required?: string[]
  anyOf?: JsonSchema[]
  $ref?: string
  $defs?: Record<string, JsonSchema>
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  minItems?: number
  maxItems?: number
  minLength?: number
  server_computed?: boolean
}

export type DerivedModelInfo = {
  kind: string
  quantity: string
  label: string
  description: string
  server_built: boolean
  needs_note: boolean
  needs_reference: boolean
}

export type MethodInfo = {
  name: string
  label: string
  description: string
  source_tier: string | null
  tier_from_payload: boolean
  destructive: boolean
  default_standard: { code: string; year?: number | null } | null
  summary_quantities: string[]
  summary_from_client: boolean
  /** The result may be left out: the record is then a document (8.106). */
  summary_optional?: boolean
  summary_kind: 'measured' | 'claimed' | null
  context_time: string
  position_required: boolean
  version: number
  derived_models: DerivedModelInfo[]
  payload_schema: JsonSchema
}

export type QuantityInfo = {
  name: string
  label: string
  unit: string | null
  kind: string
  scope: 'identity' | 'snapshot'
  ranking: string[]
  ordinal_direction: string | null
  applies_to: string[] | null
  values: string[] | null
  accepted_units: string[] | null
  mapping: Record<string, string | null>
}

let methodsPromise: Promise<MethodInfo[]> | null = null
let quantitiesPromise: Promise<QuantityInfo[]> | null = null

/** The method registry; one request per page load. */
export function loadMethods(): Promise<MethodInfo[]> {
  if (!methodsPromise) {
    methodsPromise = backendJson<MethodInfo[]>('/evidence/methods').catch((err) => {
      methodsPromise = null
      throw err
    })
  }
  return methodsPromise
}

/**
 * Help texts of the fields that are not part of a payload (position,
 * dates, "I performed this"): the descriptions of the create schema the
 * backend serves for codegen, so they also have one source.
 */
export type EnvelopeHelp = (definition: string, field: string) => string

let envelopePromise: Promise<EnvelopeHelp> | null = null

export function loadEnvelopeHelp(): Promise<EnvelopeHelp> {
  if (!envelopePromise) {
    // the create schema (codegen route) and the OpenAPI document (the upload
    // route's own field texts) are the two places the backend words them
    envelopePromise = Promise.all([
      backendJson<{ $defs?: Record<string, JsonSchema> }>('/schema/create-evidence').catch(() => null),
      backendJson<{ components?: { schemas?: Record<string, JsonSchema> } }>('/openapi.json').catch(() => null),
    ]).then(([create, openapi]) => (definition: string, field: string) =>
      create?.$defs?.[definition]?.properties?.[field]?.description
      ?? openapi?.components?.schemas?.[definition]?.properties?.[field]?.description
      ?? '')
  }
  return envelopePromise
}

/** The backend's text for the upload control (decision 8.13). */
export const UPLOAD_HELP: [string, string] = ['Body_attach_file_evidence_attachments_post', 'file']

export function loadQuantities(): Promise<QuantityInfo[]> {
  if (!quantitiesPromise) {
    quantitiesPromise = backendJson<QuantityInfo[]>('/evidence/quantities').catch((err) => {
      quantitiesPromise = null
      throw err
    })
  }
  return quantitiesPromise
}

/** A 422 of the evidence routes: `detail.errors[{path, message}]`. */
export type ProblemRow = { path: string; message: string; record?: number }

export function problemsOf(err: unknown): ProblemRow[] {
  if (!(err instanceof BackendError)) return []
  // FastAPI's own body validation: [{loc: [body, records, 0, field], msg}]
  if (Array.isArray(err.detail)) {
    return (err.detail as { loc?: unknown[]; msg?: unknown }[])
      .filter((row) => typeof row?.msg === 'string')
      .map((row) => {
        const loc = (row.loc ?? []).filter((p) => p !== 'body')
        const batch = loc[0] === 'records' && typeof loc[1] === 'number'
        const rest = batch ? loc.slice(2) : loc
        return {
          path: rest.join('.'),
          message: String(row.msg).replace(/^Value error, /, ''),
          record: batch ? (loc[1] as number) : undefined,
        }
      })
  }
  const detail = err.detail as { errors?: unknown; index?: unknown } | null
  if (!detail || typeof detail !== 'object' || !Array.isArray(detail.errors)) return []
  // a bulk names the record by its position in `index`
  const record = typeof detail.index === 'number' ? detail.index : undefined
  return (detail.errors as { path?: unknown; message?: unknown }[])
    .filter((row) => typeof row?.message === 'string')
    .map((row) => ({
      path: typeof row.path === 'string' ? row.path : '',
      message: String(row.message),
      record,
    }))
}

export async function createBulk(
  records: EvidenceBulkItem[],
  submit: boolean,
): Promise<EvidenceView[]> {
  const body = await backendJson<{ records: EvidenceView[] }>('/evidence/bulk', {
    method: 'POST',
    body: { records, submit },
  })
  return body.records
}

/**
 * `PATCH /evidence/{id}`: edit a draft (author or moderator(D)) or a pending
 * record (moderator(D)); the body is the create body without the component
 * (`editBody`). The status and the attachments stay (decision 8.127).
 */
export function patchEvidence(id: string, body: Record<string, unknown>): Promise<EvidenceView> {
  return backendJson<EvidenceView>(`/evidence/${encodeURIComponent(id)}`, { method: 'PATCH', body })
}

export type EvidenceVerb =
  | 'submit'
  | 'recall'
  | 'resubmit'
  | 'publish'
  | 'reject'
  | 'withdraw'
  | 'reinstate'

export function evidenceAction(
  id: string,
  verb: EvidenceVerb,
  body?: { reason: string },
  query = '',
): Promise<EvidenceView> {
  return backendJson<EvidenceView>(`/evidence/${encodeURIComponent(id)}/${verb}${query}`, {
    method: 'POST',
    body,
  })
}

export function putVerification(
  id: string,
  state: string,
  note?: string | null,
): Promise<EvidenceView> {
  return backendJson<EvidenceView>(`/evidence/${encodeURIComponent(id)}/verification`, {
    method: 'PUT',
    body: { state, note: note ?? null },
  })
}

export function deleteEvidence(id: string): Promise<unknown> {
  return backendJson(`/evidence/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export function loadEvidenceOf(
  identityId: string,
  query = 'status=all&include=superseded',
): Promise<EvidenceView[]> {
  return backendJson<EvidenceView[]>(
    `/identities/${encodeURIComponent(identityId)}/evidence?${query}`,
  )
}

export function loadProperties(identityId: string): Promise<PropertiesView> {
  return backendJson<PropertiesView>(`/identities/${encodeURIComponent(identityId)}/properties`)
}

export function loadPending(): Promise<PendingEvidenceItem[]> {
  return backendJson<PendingEvidenceItem[]>('/evidence/pending')
}

export type AttachmentEntry = {
  index: number
  name?: string | null
  media_type: string
  size: number
  sha256: string
  uploaded_by_user_id?: string | null
  uploaded_at?: string | null
  removed?: { at?: string | null; by_user_id?: string | null; reason?: string | null } | null
}

export function attachmentUrl(evidenceId: string, index: number): string {
  return `/api/backend/evidence/${encodeURIComponent(evidenceId)}/attachments/${index}`
}

export function loadAttachments(evidenceId: string): Promise<AttachmentEntry[]> {
  return backendJson<AttachmentEntry[]>(
    `/evidence/${encodeURIComponent(evidenceId)}/attachments`,
  )
}

export function removeAttachment(
  evidenceId: string,
  index: number,
  reason?: string,
): Promise<unknown> {
  const query = reason ? `?reason=${encodeURIComponent(reason)}` : ''
  return backendJson(
    `/evidence/${encodeURIComponent(evidenceId)}/attachments/${index}${query}`,
    { method: 'DELETE' },
  )
}

/**
 * One file to several records, stored once per record by the server
 * (decision 7.3). A 409 names exactly which records hold the file.
 */
export async function uploadAttachment(file: File, recordIds: string[]): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  form.append('record_ids', recordIds.join(','))
  const response = await fetch('/api/backend/evidence/attachments', {
    method: 'POST',
    body: form,
    credentials: 'include',
  })
  if (response.ok) return
  const text = await response.text()
  let detail: unknown = text
  try {
    const parsed = JSON.parse(text) as { detail?: unknown; error?: unknown }
    detail = parsed.detail ?? parsed.error ?? parsed
  } catch {
    // keep the text
  }
  throw new BackendError(response.status, detail)
}

/** My latest record of a method in a dataset (repeat from my last record, 7.1; decision 8.83): one request. */
export async function myLatestRecord(
  method: string | null,
  dataset: string,
): Promise<EvidenceView | null> {
  const query = new URLSearchParams({
    dataset, status: 'all', recorded_by: 'me', order: 'newest', limit: '1',
  })
  // without a method: the latest of any method (the line above the method cards)
  if (method) query.set('method', method)
  const rows = await backendJson<EvidenceView[]>(`/evidence?${query}`)
  return rows[0] ?? null
}
