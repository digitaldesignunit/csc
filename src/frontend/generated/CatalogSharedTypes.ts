// Auto-generated from backend OpenAPI schema
// Generated on: 2026-06-10T10:14:57.114Z
// Source: https://api.ddu.uber.space/schema/catalog-shared

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
  meshes?: ComponentMesh[] | unknown; // Array of mesh geometries
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


// Shared catalog value types (frames, location, design mesh geometry, etc.)
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
