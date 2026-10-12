/**
 * Ids to see and copy (decision 8.141 b): the short form that is shown in a
 * chip, and the Grasshopper parameter each kind of id goes into.
 */
export type IdKind = 'ComponentID' | 'SnapshotID' | 'RecordID'

export const SHORT_ID_LENGTH = 8

/** The first characters of an id, enough to tell ids apart on a page. */
export function shortId(id: string, length = SHORT_ID_LENGTH): string {
  const text = String(id ?? '').trim()
  return text.length > length ? text.slice(0, length) : text
}

/** What a chip says about itself: "Snapshot id" and so on. */
export const ID_KIND_LABELS: Record<IdKind, string> = {
  ComponentID: 'Component id',
  SnapshotID: 'Version id',
  RecordID: 'Record id',
}
