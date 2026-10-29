/**
 * Where a click on an evidence record of the History graph leads (issue 37):
 * a reinforcement layout with bars and a position opens in the viewer, the
 * URL of "Show in viewer" (8.178), on this piece and on another lane; any
 * other record, or a layout with nothing to draw, goes to its card.
 */
import { layoutViewerHref, type LayoutRecord } from '@/lib/reinforcementColors'

import type { HistoryEvent } from '@/lib/history/types'

export const LAYOUT_METHOD = 'reinforcement_layout'

/**
 * The record of an evidence group that holds exactly one: opening such a group
 * changes only the glyph, so the click goes on to the record (issue 37). A group
 * of several records only expands; anything else is null.
 */
export function singleRecordOf(group: HistoryEvent): HistoryEvent | null {
  if (group.kind !== 'evidence_group') return null
  const ids = group.ids ?? []
  if (ids.length !== 1 || (group.count !== undefined && group.count !== 1)) return null
  return { ...group, kind: 'evidence', id: ids[0], ids: undefined, count: undefined }
}

export type RecordTarget =
  /** open this address (a layout in the viewer) */
  | { kind: 'viewer'; href: string }
  /** the card on another lane's page: navigate there, that page scrolls once its records have loaded */
  | { kind: 'other-lane'; href: string }
  /** the card on this page; `openCorrected`: it sits behind "Show corrected records" */
  | { kind: 'card'; recordId: string; openCorrected: boolean }

export function recordTarget(input: {
  recordId: string
  method?: string | null
  laneId: string
  identityId: string
  /** the full record: needed for a layout (position, bars) and for `superseded_by` */
  record?: LayoutRecord | null
}): RecordTarget {
  const { recordId, method, laneId, identityId, record } = input
  if (method === LAYOUT_METHOD && record) {
    const href = layoutViewerHref(record)
    if (href) return { kind: 'viewer', href }
  }
  if (laneId !== identityId) {
    return { kind: 'other-lane', href: `/components/${encodeURIComponent(laneId)}#${recordAnchor(recordId)}` }
  }
  return { kind: 'card', recordId, openCorrected: Boolean(record?.superseded_by) }
}

/** The id of a card in the records list. */
export function recordAnchor(recordId: string): string {
  return `record-${encodeURIComponent(recordId)}`
}

/** The record id of an address hash `#record-<id>`, or null. */
export function recordIdOfHash(hash: string): string | null {
  const match = /^#record-(.+)$/.exec(hash)
  if (!match) return null
  try {
    return decodeURIComponent(match[1])
  } catch {
    return null
  }
}
