// Auto-generated from backend OpenAPI schema
// Generated on: 2026-06-10T12:31:17.044Z
// Source: https://api.2ndchances.build/schema/design

import { ComponentGeometry } from './CatalogSharedTypes';

export interface DesignAdditionalGeometry {
  _id?: string; // Globally unique identifier for this additional geometry item
  name?: string | unknown; // Optional human-readable name
  iframe: DesignInsertionFrame; // Insertion frame defining geometry orientation
  geometry: ComponentGeometry; // Geometry data with one or more meshes.
}

export interface DesignComponent {
  snapshot: string; // Snapshot ID (GUID) reference - a specific catalog version, not the identity's current snapshot
  iframe: DesignInsertionFrame; // Insertion frame defining snapshot placement in design space
}

export interface DesignInsertionFrame {
  o: number[]; // Origin point as [x, y, z] coordinates
  x: number[]; // X-axis vector as [x, y, z] coordinates
  y: number[]; // Y-axis vector as [x, y, z] coordinates
  z: number[]; // Z-axis vector as [x, y, z] coordinates
}

export interface DesignModel {
  _id?: string; // Globally unique design identifier (GUID)
  name?: string | unknown; // Human readable design name (optional)
  description?: string | unknown; // Design description (optional)
  creator: string; // UUID of user who created this design
  created: string; // ISO timestamp when design was created
  lastmodified: string; // ISO timestamp when design was last modified
  components: DesignComponent[]; // List of snapshot placements and their insertion frames
  additional_geometry?: DesignAdditionalGeometry[]; // List of additional static meshes embedded in the design. Always present; may be empty.
}

