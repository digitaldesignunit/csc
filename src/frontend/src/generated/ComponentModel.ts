// Auto-generated from backend OpenAPI schema
// Generated on: 2025-08-22T08:39:30.231Z
// Source: https://api.ddu.uber.space/schema/component

export interface ComponentModel {
  _id?: string; // Globally unique component identifier (GUID)
  name?: string | any; // Human readable component name (optional)
  created: string; // ISO timestamp when component was created
  lastmodified: string; // ISO timestamp when component was last modified
  type: string; // Type of component (sheet, beam, slab, rubble, column)
  material: string; // Material type of the component
  complexity?: number | any; // Complexity level (0-3, where 0 is simplest)
  fragment: boolean; // Whether this component is a fragment
  assembly: boolean; // Whether this component is an assembly
  geometry: Record<string, any>; // Component geometry data (mesh, extrusion, etc.)
  color?: number[] | any; // RGB color values as [R, G, B] integers (0-255)
  bbx: number[]; // Bounding box dimensions as [X, Y, Z] float values
  location?: Record<string, any> | any; // Geographic location data (lat/lon coordinates)
  descriptors?: Record<string, any> | any; // Component descriptors and metadata
  processes?: Record<string, any> | any; // Manufacturing or processing information
  iframe?: Record<string, any> | any; // Insertion Frame / Transformation matrix data
  attributes?: Record<string, any> | any; // Additional component attributes
  validated: boolean; // Whether this component has been validated
}

// Utility types for better type safety
export type ComponentType = 'sheet' | 'beam' | 'slab' | 'rubble' | 'column';
export type ComponentComplexity = 0 | 1 | 2 | 3;

// Type guards
export function isComponentModel(obj: any): obj is ComponentModel {
  return obj && typeof obj === 'object' && '_id' in obj && 'type' in obj;
}

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
