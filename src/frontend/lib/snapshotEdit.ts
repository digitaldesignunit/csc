/**
 * Pure parts of the "Edit details" page (spec 3.2.2, decision 8.123 c): which
 * version is on screen, which capture fields may still be filled, and the
 * `PATCH /snapshots/{sid}` body of what changed. Nothing here talks to the
 * network, so the unit test covers it.
 */
import type { Capture, ComponentSnapshot } from '@/generated/CatalogModels'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { dateOnlyToIso, isoToDateOnly } from '@/lib/lineage'
import { creditFromInputs } from '@/lib/photoCredit'
import { emptyFields, metadataPatch, type Metadata } from '@/lib/snapshotForm'

type Precision = NonNullable<ComponentSnapshot['effective_from_precision']>
type Method = NonNullable<Capture['method']>

export const CAPTURE_METHOD_LABELS: Record<Method, string> = {
  photogrammetry: 'Photogrammetry',
  lidar: 'LiDAR',
  structured_light: 'Structured light',
  manual: 'Manual',
}

/** The capture fields the page can fill; markers, fixtures and the coordinate system come with the capture tool. */
export const FILLABLE_CAPTURE = ['method', 'device', 'software', 'captured_at'] as const
export type FillableCapture = (typeof FILLABLE_CAPTURE)[number]

export type EditValues = Metadata & {
  effectiveFrom: string          // YYYY-MM-DD, or empty
  precision: Precision
  captureNotes: string
  /** The photo credit of the version (8.128 a): the text and the link. */
  creditText: string
  creditUrl: string
  method: Method | null
  device: string
  software: string
  capturedAt: string             // YYYY-MM-DD, or empty
}

export function editValuesOf(snapshot: ComponentSnapshot): EditValues {
  const color = Array.isArray(snapshot.color) && snapshot.color.length === 3
    ? (snapshot.color.map((v) => Math.round(v)) as [number, number, number])
    : emptyFields().color
  const capture = snapshot.capture ?? {}
  const credit = (snapshot as { photo_credit?: { text?: string | null; url?: string | null } | null }).photo_credit
  return {
    name: snapshot.name ?? '',
    notes: snapshot.notes ?? '',
    color,
    lat: snapshot.location ? String(snapshot.location.lat) : '',
    lon: snapshot.location ? String(snapshot.location.lon) : '',
    effectiveFrom: isoToDateOnly(snapshot.effective_from),
    precision: snapshot.effective_from_precision ?? 'day',
    captureNotes: capture.notes ?? '',
    creditText: credit?.text ?? '',
    creditUrl: credit?.url ?? '',
    method: capture.method ?? null,
    device: capture.device ?? '',
    software: capture.software ?? '',
    capturedAt: isoToDateOnly(capture.captured_at),
  }
}

const hasValue = (value: unknown) => value !== null && value !== undefined && value !== ''

/**
 * The capture fields of a version that are still empty: the only ones that
 * may be filled in place, once (8.123 a). A field that is set is read-only
 * here and changes by "Correct a version".
 */
export function emptyCaptureFields(snapshot: Pick<ComponentSnapshot, 'capture'>): FillableCapture[] {
  const capture = snapshot.capture ?? {}
  return FILLABLE_CAPTURE.filter((name) => !hasValue(capture[name]))
}

/**
 * The `PATCH /snapshots/{sid}` body: only what changed; `undefined` when the
 * location text is not a location. A capture field that was set is never
 * sent; `capture.notes` is a note and stays editable.
 */
export function editPatch(
  snapshot: ComponentSnapshot,
  before: EditValues,
  after: EditValues,
): Record<string, unknown> | undefined {
  const patch = metadataPatch(before, after)
  if (patch === undefined) return undefined
  if (after.effectiveFrom !== before.effectiveFrom) {
    const at = dateOnlyToIso(after.effectiveFrom)
    if (at) patch.effective_from = at
  }
  if (after.precision !== before.precision && after.effectiveFrom) patch.effective_from_precision = after.precision
  if (after.creditText.trim() !== before.creditText.trim() || after.creditUrl.trim() !== before.creditUrl.trim()) {
    patch.photo_credit = creditFromInputs(after.creditText, after.creditUrl)   // no text: cleared
  }
  const capture: Record<string, unknown> = {}
  if (after.captureNotes.trim() !== before.captureNotes.trim()) capture.notes = after.captureNotes.trim() || null
  const open = new Set(emptyCaptureFields(snapshot))
  if (open.has('method') && after.method && after.method !== before.method) capture.method = after.method
  if (open.has('device') && after.device.trim()) capture.device = after.device.trim()
  if (open.has('software') && after.software.trim()) capture.software = after.software.trim()
  if (open.has('captured_at') && after.capturedAt) capture.captured_at = dateOnlyToIso(after.capturedAt)
  if (Object.keys(capture).length) patch.capture = capture
  return patch
}

/** The version the page opens on: the one asked for, else the current one, else the latest. */
export function versionToEdit(rows: SnapshotSummaryItem[], asked: string | null | undefined): SnapshotSummaryItem | undefined {
  if (asked) {
    const wanted = rows.find((row) => row._id === asked)
    if (wanted) return wanted
  }
  return rows.find((row) => row.is_current) ?? [...rows].sort((a, b) => b.version - a.version)[0]
}

/** One line of the version choice: "v2 (published, current), a correction of v0". */
export function versionLabel(row: SnapshotSummaryItem, rows: SnapshotSummaryItem[]): string {
  const parts: string[] = [row.status]
  if (row.is_current) parts.push('current')
  if (row.superseded_by) parts.push('corrected')
  let text = `v${row.version} (${parts.join(', ')})`
  if (row.supersedes) {
    const byId = new Map(rows.map((r) => [r._id, r]))
    let root = byId.get(row.supersedes)
    for (let guard = 0; root?.supersedes && guard < 50; guard += 1) root = byId.get(root.supersedes) ?? undefined
    if (root) text += `, a correction of v${root.version}`
  }
  return text
}
