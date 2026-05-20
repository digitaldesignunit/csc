// Auto-generated from backend OpenAPI schema
// Generated on: 2026-05-20T14:18:20.804Z
// Source: https://api.ddu.uber.space/schema/catalog-compose

import type {
  ComponentBoundingBox,
  ComponentFrame,
  ComponentLocation,
} from './ComponentModel';

export interface ComponentIdentity {
  _id?: string; // Globally unique identity identifier (GUID)
  catalog_number: number; // Monotonic human-facing catalog number; never recycled. Display as 'CSC-' + six-digit zero-padded decimal.
  type: string; // Type of component. Must be one of ALLOWED_COMPONENT_TYPES.
  material: string; // Material type of the component
  dataset: string; // Dataset name that this component belongs to
  manufactured_at?: string | unknown; // ISO-8601 timestamp (UTC) describing when the component was originally manufactured, to the precision indicated by `manufactured_precision`.
  manufactured_precision?: string | unknown; // Precision qualifier for `manufactured_at`. Must be one of ALLOWED_MANUFACTURED_PRECISIONS.
  salvage_source?: string | unknown; // Short free-text description of where the component was salvaged from (e.g. building name, demolition site).
  salvaged_at?: string | unknown; // ISO-8601 timestamp (UTC) describing when the component was salvaged. Paired with `salvage_source`.
  reserved?: string; // UUID of user who has reserved this component (empty if not reserved)
  attributes?: Record<string, unknown> | unknown; // Additional static metadata about the physical piece
  parent_identities?: string[] | unknown; // UUIDs of immediate parent identities. Single-element for 1:1 splits; multi-element for N:1 merges. `None` if no known parent.
  consumed_at?: string | unknown; // ISO-8601 timestamp when the physical piece ceased to exist as a discrete object (split, demolished, returned). `None` = active.
  current_snapshot_id: string; // UUID of the snapshot in `component_snapshots` that represents the current state of this identity.
  created: string; // ISO timestamp when this identity was first recorded
  lastmodified: string; // ISO timestamp when this identity was last modified
}

export interface ComponentSnapshot {
  _id?: string; // Globally unique snapshot identifier (GUID)
  identity_id: string; // UUID of the ComponentIdentity this snapshot belongs to
  version: number; // Per-identity monotonic version, zero-based. First snapshot for an identity is `0`. Unique on (identity_id, version). Server-assigned: never accept this field from client payloads; the backend computes it (`0` on initial create, `max(existing)+1` on snapshot evolution).
  virtual?: boolean; // True when this snapshot represents a hypothetical / proposal (not yet realized on the physical piece). Migrated snapshots from legacy are `False`.
  name?: string | unknown; // Human readable name for this state (can change across snapshots, e.g. on remanufacturing).
  geometry: SnapshotGeometry; // Multi-representation geometry block for this snapshot (meshes, point clouds, extrusions, marker_points). At least one of meshes / point_clouds / extrusions must be non-empty.
  descriptors?: Record<string, unknown> | unknown; // Descriptors computed from this snapshot's geometry
  bbx: ComponentBoundingBox; // Bounding box [X, Y, Z] for this snapshot's geometry
  bbx_origin: number[]; // Bounding box origin [X, Y, Z] in PCA space
  complexity: number; // Complexity level (0-3); derived from geometry
  fragment: boolean; // Whether this snapshot's state is a fragment
  assembly: boolean; // Whether this snapshot's state is an assembly
  condition?: number | unknown; // Condition grade for this state. 0 = destroyed/retired, 1 = poor, 2 = average, 3 = good. `None` = unknown.
  color?: number[] | unknown; // RGB rendering color as [R, G, B] integers (0-255)
  location?: ComponentLocation | unknown; // Geographic location of the piece at the time of this snapshot. PATCH-able on the current snapshot without creating a new one.
  processes?: Record<string, unknown> | unknown; // Manufacturing or processing information for this state
  iframe: ComponentFrame; // Insertion frame / transformation matrix for this state
  pca_frame: ComponentFrame; // PCA frame / principal-component transformation for this state
  validated: boolean; // Whether this snapshot's state has been validated
  etag?: string | unknown; // ETag for cache validation; recomputed from snapshot content.
  photo_count?: number | unknown; // Number of user-uploaded photos on disk for this snapshot; optional cache for list UI
  added_by_user_id?: string | unknown; // User id of whoever created this snapshot (set on v0 create; records who added the identity to the catalog)
  added_by_username?: string | unknown; // Username at create time (display cache for added_by_user_id)
  notes?: string | unknown; // Free-text notes for this snapshot state
  quantity?: number; // Number of identical physical items represented by this catalog entry (e.g. a batch of matching fixtures)
  mesh_ply_resolutions?: Record<string, unknown> | unknown; // Which resolution files exist on disk per mesh primitive index (string keys '0', '1', … matching ``geometry.meshes``). Values list role names: typically 'reduced', optionally 'detailed'. Paths: ``meshes/<snapshot_id>/<i>/reduced.ply`` and ``.../detailed.ply``. Example: {'0': ['reduced', 'detailed']}.
  created: string; // ISO timestamp when this snapshot was created
  lastmodified: string; // ISO timestamp when this snapshot was last modified
}

export interface SnapshotExtrusion {
  profile: number[][]; // 2D profile polyline as array of [x, y] coordinate pairs (centered in XY)
  height: number; // Extrusion length along Z
}

export interface SnapshotGeometry {
  meshes?: SnapshotMesh[] | unknown; // Mesh primitives; optional PLY files under ``meshes/<snapshot_id>/<i>/{reduced,detailed}.ply``
  point_clouds?: SnapshotPointCloud[] | unknown; // Array of point cloud primitives (each backed by a PLY file)
  extrusions?: SnapshotExtrusion[] | unknown; // Array of extrusion primitives (profile + height; fully inline)
  marker_points?: number[][] | unknown; // Shared marker points as array of [x, y, z] coordinate triplets; same coordinate frame as the meshes/point_clouds/extrusions
}

export interface SnapshotMesh {
  vertices: number[][]; // Mesh vertices as [x, y, z] in Rhino Z-up (CSC canonical frame)
  faces: number[][]; // Mesh faces as array of vertex index lists (triangles or polygons)
  colors?: number[][] | unknown; // Optional per-vertex RGB colors as [r, g, b] integers (0-255); parallel to vertices when present
}

export interface SnapshotPointCloud {
  points: number[][]; // Point cloud points as array of [x, y, z] coordinates
  colors?: number[][] | unknown; // Optional per-point RGB colors as [r, g, b] integers (0-255); parallel to points when present
}

export interface ComposeIdentityResponse {
  identity: ComponentIdentity;
  snapshot: ComponentSnapshot;
}

/** Canonical read model: `GET /identities/{id}/compose` (same JSON as the API). */
export type CatalogComponent = ComposeIdentityResponse

