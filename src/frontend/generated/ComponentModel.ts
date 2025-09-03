// Auto-generated from backend OpenAPI schema
// Generated on: 2025-09-03T12:35:25.796Z
// Source: https://api.ddu.uber.space/schema/component

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
  geometry: Record<string, unknown>; // Component geometry data (mesh, extrusion, etc.)
  color?: number[] | unknown; // RGB color values as [R, G, B] integers (0-255)
  bbx: number[]; // Bounding box maximum extents as [X, Y, Z] float values (dimensions of the component)
  location?: Record<string, unknown> | unknown; // Geographic location data (lat/lon coordinates)
  descriptors?: Record<string, unknown> | unknown; // Component descriptors and metadata
  processes?: Record<string, unknown> | unknown; // Manufacturing or processing information
  iframe?: Record<string, unknown> | unknown; // Insertion Frame / Transformation matrix data
  pca_frame?: Record<string, unknown> | unknown; // PCA Frame / Principal Component Analysis transformation matrix data
  reserved?: string | unknown; // UUID of user who has reserved this component (empty if not reserved)
  attributes?: Record<string, unknown> | unknown; // Additional component attributes
  validated: boolean; // Whether this component has been validated
}

// Utility types for better type safety
export type ComponentType = 'sheet' | 'beam' | 'slab' | 'rubble' | 'column';
export type ComponentComplexity = 0 | 1 | 2 | 3;
export type ComponentBoundingBox = Array<number>
export type ComponentPolylinePoints = Array<Array<number>>
export type ComponentMeshVertices = Array<Array<number>>
export type ComponentMeshFaces = Array<Array<number>>
export type ComponentMeshColors = Array<Array<number>>
export type ComponentLocation = {
  lat: number,
  lon: number
}

// Type guards
export function isComponentModel(obj: unknown): obj is ComponentModel {
  return obj !== null && 
         typeof obj === 'object' && 
         '_id' in obj && 
         'type' in obj;
}
export function isValidBoundingBox(bbx: unknown): bbx is ComponentBoundingBox {
  return Array.isArray(bbx) && 
         bbx.length >= 3 && 
         bbx.every(val => typeof val === 'number' && !isNaN(val))
}
export function isMeshGeometry(geometry: unknown): geometry is { mesh: { v: number[][], f: number[][], c: number[][] } } {
  return geometry !== null && 
         typeof geometry === 'object' && 
         'mesh' in geometry &&
         geometry.mesh !== null &&
         typeof geometry.mesh === 'object' &&
         'v' in geometry.mesh && 'f' in geometry.mesh && 'c' in geometry.mesh;
}
export function isExtrusionGeometry(geometry: unknown): geometry is { extrusion: { profile: number[][], height: number } } {
  return geometry !== null && 
         typeof geometry === 'object' && 
         'extrusion' in geometry &&
         geometry.extrusion !== null &&
         typeof geometry.extrusion === 'object' &&
         'profile' in geometry.extrusion && 'height' in geometry.extrusion;
}

// Extension types
export interface ExtendedComponentModel extends ComponentModel {
  reserved_by_username?: string;
}

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
