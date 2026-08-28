/**
 * Catalog types that are not a single Pydantic root on the backend.
 *
 * - **CatalogShallowRow**: merged row from `GET /identities?expand=shallow` (see
 *   `merge_shallow_catalog_row`); keep aligned with that projection.
 * - **SnapshotMeshRouting** + **snapshotMeshRoutingFromSnapshot**: small client helper
 *   for PLY mesh URLs (not duplicated as a dedicated API model).
 */

import type {
  ComponentSnapshot,
  ComposeIdentityResponse,
} from './CatalogModels'

/** Row shape from `GET /identities` with `expand=shallow` (not a full compose payload). */
export type CatalogShallowRow = {
  _id?: string
  type?: string
  material?: string
  dataset?: string
  reserved?: string
  catalog_number?: number
  /** Set when the physical piece is consumed (archived); null = active in catalog */
  consumed_at?: string | null
  current_snapshot_id?: string
  name?: unknown
  created?: string
  lastmodified?: string
  complexity?: number
  fragment?: boolean
  assembly?: boolean
  validated?: boolean
  color?: unknown
  bbx?: number[]
  bbx_origin?: number[]
  condition?: number | unknown
  location?: unknown
  processes?: Record<string, unknown> | unknown
  iframe?: unknown
  pca_frame?: unknown
  etag?: string | unknown
  virtual?: boolean
  version?: number
  identity_id?: string
  reserved_by_username?: string | null
}

export type ProvenanceIdentityNode = {
  id: string
  kind: 'identity'
  identity_id: string
  catalog_number?: number | null
  name?: string | null
  type?: string | null
  consumed_at?: string | null
  is_root: boolean
}

export type ProvenanceSnapshotNode = {
  id: string
  kind: 'snapshot'
  snapshot_id: string
  identity_id: string
  version: number
  virtual?: boolean
  validated: boolean
  is_current: boolean
  name?: string | null
}

export type ProvenanceGraphNode = ProvenanceIdentityNode | ProvenanceSnapshotNode

export type ProvenanceGraphEdge = {
  id: string
  source: string
  target: string
  kind: 'parent' | 'has_snapshot' | 'version'
}

/** Payload from `GET /identities/{id}/provenance`. */
export type ProvenanceGraph = {
  root_identity_id: string
  nodes: ProvenanceGraphNode[]
  edges: ProvenanceGraphEdge[]
}

/** For `GET /snapshots/{id}/meshes/…` PLY routing. */
export type SnapshotMeshRouting = {
  snapshot_id: string
  mesh_ply_resolutions?: Record<string, string[]> | null
}

/** First snapshot in a compose payload (the active row for detail views). */
export function primarySnapshot(
  catalog: Pick<ComposeIdentityResponse, 'snapshots'>,
): ComponentSnapshot {
  const snap = catalog.snapshots?.[0]
  if (!snap) {
    throw new Error('Compose payload has no snapshots')
  }
  return snap
}

export function snapshotMeshRoutingFromSnapshot(
  snapshot: Pick<ComponentSnapshot, '_id' | 'mesh_ply_resolutions'>,
): SnapshotMeshRouting {
  const raw = snapshot.mesh_ply_resolutions
  return {
    snapshot_id: snapshot._id as string,
    mesh_ply_resolutions:
      raw === undefined || raw === null
        ? null
        : (raw as Record<string, string[]>),
  }
}
