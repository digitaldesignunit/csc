/**
 * Catalog types that are not a single Pydantic root on the backend.
 *
 * - **CatalogShallowRow**: alias of the generated `CatalogRow` (list rows).
 * - **SnapshotMeshRouting** + **snapshotMeshRoutingFromSnapshot**: small client helper
 *   for PLY mesh URLs (not duplicated as a dedicated API model).
 */

import type {
  CatalogRow,
  ComponentSnapshot,
  ComponentPassport,
} from './CatalogModels'

/** Row from `GET /identities` (`expand=shallow`): the generated `CatalogRow`. */
export type CatalogShallowRow = CatalogRow

export type ProvenanceIdentityNode = {
  id: string
  kind: 'identity'
  identity_id: string
  catalog_number?: number | null
  name?: string | null
  original_function?: string | null
  /** `exit.kind` when the piece left circulation, else null */
  exit_kind?: string | null
  is_root: boolean
}

export type ProvenanceSnapshotNode = {
  id: string
  kind: 'snapshot'
  snapshot_id: string
  identity_id: string
  version: number
  status: string
  superseded: boolean
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

/** Feature basis for `GET /identities/map`. */
export type ComponentMapBasis = 'radial_signature' | 'scalars'

/** Embedding method for `GET /identities/map`. */
export type ComponentMapMethod = 'pca' | 'umap'

export type ComponentMapPoint = {
  id: string
  x: number
  y: number
  name?: string | null
  original_function?: string | null
  catalog_number?: number | null
  color?: unknown
}

/** Payload from `GET /identities/map`. */
export type ComponentMapResponse = {
  basis: ComponentMapBasis
  basis_label: string
  method: ComponentMapMethod
  requested_method: ComponentMapMethod
  total: number
  displayed: number
  points: ComponentMapPoint[]
  cached?: boolean
  source?: 'cache' | 'live'
  computed_at?: string | null
}

/** For `GET /snapshots/{id}/meshes/...` PLY routing. */
export type SnapshotMeshRouting = {
  snapshot_id: string
  mesh_ply_resolutions?: Record<string, string[]> | null
}

/**
 * First snapshot in a passport payload (the active row for detail views).
 * A published identity may have none left (all withdrawn, decision 8.17).
 */
export function primarySnapshot(
  catalog: Pick<ComponentPassport, 'snapshots'>,
): ComponentSnapshot {
  const snap = catalog.snapshots?.[0]
  if (!snap) {
    throw new Error('Passport payload has no snapshots')
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
