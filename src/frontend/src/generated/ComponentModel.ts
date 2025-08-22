// Auto-generated from backend OpenAPI schema
// Generated on: 2025-08-22T11:01:41.587Z
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
  bbx: number[]; // Bounding box dimensions as [X, Y, Z] float values
  location?: Record<string, unknown> | unknown; // Geographic location data (lat/lon coordinates)
  descriptors?: Record<string, unknown> | unknown; // Component descriptors and metadata
  processes?: Record<string, unknown> | unknown; // Manufacturing or processing information
  iframe?: Record<string, unknown> | unknown; // Insertion Frame / Transformation matrix data
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

// Partial type for updates
export type PartialComponentModel = Partial<ComponentModel>;
