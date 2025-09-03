// Auto-generated from backend OpenAPI schema
// Generated on: 2025-09-03T13:03:38.706Z
// Source: https://api.ddu.uber.space/schema/component

export interface ComponentExtrusion {
  profile: number[][]; // Extrusion profile points
  height: number; // Extrusion height
}

export interface ComponentFrame {
  o: number[]; // Origin point [x, y, z]
  x: number[]; // X axis vector [x, y, z]
  y: number[]; // Y axis vector [x, y, z]
  z: number[]; // Z axis vector [x, y, z]
}

export interface ComponentGeometry {
  mesh?: ComponentMesh | unknown; // Mesh geometry
  extrusion?: ComponentExtrusion | unknown; // Extrusion geometry
}

export interface ComponentLocation {
  lat: number; // Latitude coordinate
  lon: number; // Longitude coordinate
}

export interface ComponentMesh {
  v: number[][]; // Mesh vertices
  f: number[][]; // Mesh faces
  c?: number[][] | unknown; // Mesh vertex colors
}

export interface ComponentModel {
  _id?: string; // Globally unique component identifier (GUID)
  name?: string | unknown; // Human readable component name (optional)
  created: string; // ISO timestamp when component was created
  lastmodified: string; // ISO timestamp when component was last modified
  type: string; // Type of component (sheet, beam, slab, rubble, column)
  material: string; // Material type of the component
  complexity?: number | unknown; // Complexity level (0-3, where 0 is simplest)
  fragment: boolean; // Whether this component is a fragment
  assembly: boolean; // Whether this component is an assembly
  geometry: ComponentGeometry; // Component geometry data (mesh, extrusion, etc.)
  color?: number[] | unknown; // RGB color values as [R, G, B] integers (0-255)
  bbx: number[]; // Bounding box maximum extents as [X, Y, Z] float values (dimensions of the component)
  location?: ComponentLocation | unknown; // Geographic location data (lat/lon coordinates)
  descriptors?: Record<string, unknown> | unknown; // Component descriptors and metadata
  processes?: Record<string, unknown> | unknown; // Manufacturing or processing information
  iframe?: ComponentFrame | unknown; // Insertion Frame / Transformation matrix data
  pca_frame?: ComponentFrame | unknown; // PCA Frame / Principal Component Analysis transformation matrix data
  reserved?: string | unknown; // UUID of user who has reserved this component (empty if not reserved)
  attributes?: Record<string, unknown> | unknown; // Additional component attributes
  validated: boolean; // Whether this component has been validated
}

// Utility types for better type safety
export type ComponentType = 'sheet' | 'beam' | 'slab' | 'rubble' | 'column';
export type ComponentComplexity = 0 | 1 | 2 | 3;

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
