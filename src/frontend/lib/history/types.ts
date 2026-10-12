/**
 * The response of `GET /identities/{id}/history` (data model spec 7.9,
 * decision 8.140 g): lanes, their events, and the links between lanes.
 */
export type HistoryEventKind =
  | 'origin'
  | 'version'
  | 'evidence_group'
  | 'evidence'
  | 'exit'
  | 'withdrawal'

export type HistoryEvent = {
  kind: HistoryEventKind
  /** ISO time; null for an undated event */
  at: string | null
  precision?: string | null
  /** version, evidence: the record id */
  id?: string
  version?: number
  status?: string
  name?: string | null
  /** a version a correction replaced */
  corrected?: boolean
  /** the id of what a correction replaces */
  corrects?: string | null
  withdrawn?: boolean
  /** origin and exit: the kind */
  detail?: string | null
  planned?: boolean
  /** origin and exit of an earlier cycle */
  cycle?: number | null
  /** evidence_group */
  count?: number
  ids?: string[]
  statuses?: string[]
  day?: string
  method?: string
  quantity?: string | null
  /** set by the client: the group a record was opened from */
  groupKey?: string
}

export type HistoryLane = {
  id: string
  level: number
  role: 'parent' | 'piece' | 'child'
  visible: boolean
  label?: string | null
  catalog_number?: number | null
  name?: string | null
  dataset?: string | null
  withdrawn?: boolean
  withdrawn_at?: string | null
  exited?: boolean
  in_place?: boolean
  events?: HistoryEvent[]
}

export type HistoryLink = {
  kind: 'cut' | 'assemble'
  from: string
  to: string
  at?: string | null
  precision?: string | null
  /** the child's first version */
  version_id?: string | null
}

export type HistoryResponse = {
  root: string
  depth: number
  expand: 'groups' | 'all'
  lanes: HistoryLane[]
  links: HistoryLink[]
  /** lanes left out beyond twelve */
  more: number
}

/** The layers of the History card applied to the graph (8.102). */
export type HistoryLayers = { lineage: boolean; states: boolean; evidence: boolean }
