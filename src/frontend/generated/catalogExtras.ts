/**
 * Catalog types that are not a single Pydantic root on the backend.
 *
 * - **CatalogShallowRow**: merged row from `GET /identities?expand=shallow` (see
 *   `merge_shallow_catalog_row`); keep aligned with that projection.
 * - **SnapshotMeshRouting** + **snapshotMeshRoutingFromSnapshot**: small client helper
 *   for PLY mesh URLs (not duplicated as a dedicated API model).
 */

import type { ComponentSnapshot } from './CatalogModels'

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

/** For `GET /snapshots/{id}/meshes/…` PLY routing. */
export type SnapshotMeshRouting = {
  snapshot_id: string
  mesh_ply_resolutions?: Record<string, string[]> | null
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
