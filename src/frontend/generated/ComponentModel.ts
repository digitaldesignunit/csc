// Auto-generated from backend OpenAPI schema
// Generated on: 2026-04-23T12:13:23.327Z
// Source: https://api.ddu.uber.space/schema/component

export type ComponentBoundingBox = number[];


export interface ComponentExtrusion {
  profile: ComponentPolylinePoints; // Extrusion profile points
  height: number; // Extrusion height
}

export interface ComponentFrame {
  o: number[]; // Origin point [x, y, z]
  x: number[]; // X axis vector [x, y, z]
  y: number[]; // Y axis vector [x, y, z]
  z: number[]; // Z axis vector [x, y, z]
}

export interface ComponentGeometry {
  mesh?: ComponentMesh | unknown; // Mesh geometry (single mesh - backward compat)
  meshes?: ComponentMesh[] | unknown; // Array of mesh geometries (multiple meshes)
  extrusion?: ComponentExtrusion | unknown; // Extrusion geometry
}

export interface ComponentLocation {
  lat: number; // Latitude coordinate
  lon: number; // Longitude coordinate
}

export interface ComponentMesh {
  v: ComponentMeshVertices; // Mesh vertices
  f: ComponentMeshFaces; // Mesh faces
  c?: ComponentMeshColors | unknown; // Mesh vertex colors
}

export type ComponentMeshColors = number[][];


export type ComponentMeshFaces = number[][];


export type ComponentMeshVertices = number[][];


export type ComponentPolylinePoints = number[][];


export interface ComponentModel {
  _id?: string; // Globally unique component identifier (GUID)
  name?: string | unknown; // Human readable component name (optional)
  created: string; // ISO timestamp when component was created
  lastmodified: string; // ISO timestamp when component was last modified
  type: string; // Type of component. Must be one of ALLOWED_COMPONENT_TYPES (panel, beam, column, slab, rubble, brick, pipe, profile, connector, other).
  material: string; // Material type of the component
  dataset: string; // Dataset name that this component belongs to
  complexity: number; // Complexity level (0-3, where 0 is simplest)
  fragment: boolean; // Whether this component is a fragment
  assembly: boolean; // Whether this component is an assembly
  geometry: ComponentGeometry; // Component geometry data (mesh, extrusion, etc.)
  color?: number[] | unknown; // RGB color values as [R, G, B] integers (0-255)
  bbx: ComponentBoundingBox; // Bounding box maximum extents as [X, Y, Z] float values (dimensions of the component)
  bbx_origin: number[]; // Bounding box center/origin as [X, Y, Z] float values (vector from world origin to bbx center in PCA space)
  location?: ComponentLocation | unknown; // Geographic location data (lat/lon coordinates)
  descriptors?: Record<string, unknown> | unknown; // Component descriptors and metadata
  processes?: Record<string, unknown> | unknown; // Manufacturing or processing information
  iframe?: ComponentFrame; // Insertion Frame / Transformation matrix data
  pca_frame?: ComponentFrame; // PCA Frame / Principal Component Analysis transformation matrix data
  reserved?: string; // UUID of user who has reserved this component (empty if not reserved)
  attributes?: Record<string, unknown> | unknown; // Additional component attributes
  marker_points?: number[][] | unknown; // Marker points as array of [x, y, z] coordinate triplets
  validated: boolean; // Whether this component has been validated
  etag?: string | unknown; // ETag for cache validation (auto-generated from lastmodified and key fields)
  condition?: number | unknown; // Condition grade. 0 = destroyed/retired, 1 = poor, 2 = average, 3 = good. `None` = unknown / unassessed.
  manufactured_at?: string | unknown; // ISO-8601 timestamp (UTC) describing when the component was originally manufactured, to the precision indicated by `manufactured_precision`. Optional.
  manufactured_precision?: string | unknown; // Precision qualifier for `manufactured_at`. Must be one of ALLOWED_MANUFACTURED_PRECISIONS (exact, month, year, unknown).
  salvage_source?: string | unknown; // Short free-text description of where the component was salvaged from (e.g. building name, demolition site).
  salvaged_at?: string | unknown; // ISO-8601 timestamp (UTC) describing when the component was salvaged. Optional. Paired with `salvage_source`.
  parent_component?: string | unknown; // Optional UUID of the parent component this component was derived from (e.g. when a piece is split into smaller pieces and reintroduced into the catalog).
}

// Utility types for better type safety
export type ComponentType =
  | 'panel'
  | 'beam'
  | 'column'
  | 'slab'
  | 'rubble'
  | 'brick'
  | 'pipe'
  | 'profile'
  | 'connector'
  | 'other';
export type ComponentComplexity = 0 | 1 | 2 | 3;
export type ComponentCondition = 0 | 1 | 2 | 3;
export type ComponentManufacturedPrecision = 'exact' | 'month' | 'year' | 'unknown';

// Type guards
export function isComponentModel(obj: unknown): obj is ComponentModel {
  return obj !== null && 
         typeof obj === 'object' && 
         '_id' in obj && 
         'type' in obj;
}

// Extension types
export interface ExtendedComponentModel extends ComponentModel {
  reserved_by_username?: string;
}

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
