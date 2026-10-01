// Auto-generated from backend OpenAPI schema
// Generated on: 2026-09-30T14:46:19.278Z
// Source: http://127.0.0.1:8000/schema/catalog-compose

import type {
  Frame,
  GeoLocation,
  Geometry,
} from './CatalogSharedTypes';

export interface Accreditation {
  scheme: 'iso_17025' | 'notified_body'; // iso_17025 = laboratory accreditation (e.g. DAkkS); notified_body = CPR notified body (Art 52 number)
  id: string; // Accreditation or notified-body number
  body: string; // Accrediting or notifying authority
  scope: string[]; // Standards the accreditation covers
  valid_until?: string | null;
}

export interface Actor {
  kind: 'user' | 'person' | 'organization';
  user_id?: string | null;
  name?: string | null;
  organization?: string | null;
  organization_ror?: string | null;
  orcid?: string | null;
  email?: string | null;
  role?: 'operator' | 'supervisor' | 'laboratory' | 'client' | 'witness' | null;
  accreditation?: Accreditation | null;
  redacted_at?: string | null;
}

export interface Capture {
  method?: 'photogrammetry' | 'lidar' | 'structured_light' | 'manual' | null;
  device?: string | null;
  software?: string | null;
  captured_at?: string | null;
  notes?: string | null;
  coordinate_system?: CoordinateSystem | null;
  markers?: Marker[];
  fixtures?: Fixture[];
}

export interface ComponentIdentity {
  _id: string;
  catalog_number: number;
  original_function: 'IfcBeam' | 'IfcColumn' | 'IfcSlab' | 'IfcPlate' | 'IfcWall' | 'IfcMember' | 'IfcPipeSegment' | 'IfcFooting' | 'IfcDiscreteAccessory' | 'IfcBuildingElementPart' | 'IfcBuildingElementProxy' | 'CscDebris';
  material: string; // FK -> materials._id (I25)
  material_class: string;
  material_class_source?: 'derived' | 'assigned';
  trade_name?: string | null;
  dataset: string; // FK -> datasets._id (I20)
  manufactured_at?: string | null;
  manufactured_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  origin?: Origin | null;
  parent_identities?: string[] | null;
  inherited_fields?: string[];
  inherited_from?: string | null;
  exit?: Exit | null;
  past_cycles?: PastCycle[];
  withdrawn?: Withdrawn | null;
  reserved?: string;
  is_public?: boolean;
  current_snapshot_id?: string | null;
  properties?: Record<string, unknown>;
  properties_version?: number;
  attributes?: Record<string, unknown>;
  created_by_user_id: string;
  created: string;
  lastmodified: string;
}

export interface ComponentSnapshot {
  _id: string;
  identity_id: string;
  version: number;
  status: 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn';
  status_changed_by_user_id?: string | null;
  status_changed_at?: string | null;
  supersedes?: string | null;
  superseded_by?: string | null;
  name?: string | null;
  effective_from: string;
  effective_from_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  shape_class?: 'linear' | 'planar' | 'block' | 'irregular' | 'composite' | null;
  shape_class_source?: 'derived' | 'assigned' | null;
  geometry: Geometry;
  capture?: Capture | null;
  descriptors?: Record<string, unknown>;
  properties?: Record<string, unknown>;
  properties_version?: number;
  frame?: Frame | null;
  bbx?: number[] | null;
  complexity?: number | null;
  complexity_source?: 'derived' | 'assigned' | null;
  fragment?: boolean;
  color?: number[] | null;
  location?: GeoLocation | null;
  notes?: string | null;
  quantity?: number;
  added_by_user_id: string;
  added_by_username?: string | null;
  photo_count?: number;
  mesh_ply_resolutions?: Record<string, unknown>;
  etag?: string | null;
  created: string;
  lastmodified: string;
}

export interface ConstructionWork {
  name: string;
  identifier?: string | null;
  year_built?: number | null;
  use?: string | null;
}

export interface CoordinateSystem {
  name: string;
  description?: string | null;
}

export interface Exit {
  kind: 'split' | 'merged' | 'installed' | 'recycled' | 'disposed' | 'returned' | 'lost';
  at: string;
  at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  construction_work?: ConstructionWork | null;
  notes?: string | null;
  recorded_by_user_id?: string | null;
}

export interface Fixture {
  label: string;
  file: string;
}

export interface Marker {
  label: string;
  role: 'rig' | 'component';
  point: number[];
}

export interface Origin {
  kind: 'deinstallation' | 'demolition' | 'offcut' | 'surplus' | 'unknown';
  at?: string | null;
  at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  place?: Place | null;
  construction_work?: ConstructionWork | null;
  method?: string | null;
  performed_by?: Actor[];
  notes?: string | null;
}

export interface PastCycle {
  origin?: Origin | null;
  exit: Exit;
}

export interface Place {
  name?: string | null;
  address?: string | null;
  location?: GeoLocation | null;
}

export interface PropertyValue {
  range: number | string[];
  unit?: string | null;
  confidence: number;
  source: 'destructive' | 'ndt' | 'archival' | 'visual' | 'heuristic' | 'inherited';
  n: number;
  evidence_ids?: string[];
  inherited_from?: string[] | null;
  derived_at: string;
}

export interface Withdrawn {
  at: string;
  by_user_id: string;
  reason: string;
  duplicate_of?: string | null;
}

export interface ComponentPassport {
  identity: ComponentIdentity;
  snapshots: ComponentSnapshot[];
}

/** Canonical read model: `GET /identities/{id}/compose` (same JSON as the API). */
export type CatalogComponent = ComponentPassport


export interface CatalogRow {
  _id: string;
  catalog_number: number;
  original_function: string;
  material: string;
  material_class: string;
  trade_name?: string | null;
  dataset: string;
  origin?: Origin | null;
  exit?: Exit | null;
  reserved?: string;
  reserved_by_username?: string | null;
  is_public?: boolean;
  current_snapshot_id?: string | null;
  identity_id: string;
  version: number;
  status: 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn';
  name?: string | null;
  effective_from?: string | null;
  effective_from_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown' | null;
  shape_class?: 'linear' | 'planar' | 'block' | 'irregular' | 'composite' | null;
  complexity?: number | null;
  fragment?: boolean;
  quantity?: number;
  color?: number[] | null;
  location?: GeoLocation | null;
  bbx?: number[] | null;
  frame?: Frame | null;
  etag?: string | null;
  created: string;
  lastmodified: string;
}

