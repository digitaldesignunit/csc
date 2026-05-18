// Auto-generated from backend OpenAPI schema
// Generated on: 2026-05-18T14:27:36.840Z
// Source: https://api.ddu.uber.space/schema/design

import { ComponentGeometry } from './ComponentModel';

export interface DesignAdditionalGeometry {
  _id?: string; // Globally unique identifier for this additional geometry item
  name?: string | unknown; // Optional human-readable name
  iframe: DesignInsertionFrame; // Insertion frame defining geometry orientation
  geometry: ComponentGeometry; // Geometry data with one or more meshes.
}

export interface DesignComponent {
  component: string; // Component ID (GUID) reference
  iframe: DesignInsertionFrame; // Insertion frame defining component orientation
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
  components: DesignComponent[]; // List of components and their insertion frames
  additional_geometry?: DesignAdditionalGeometry[]; // List of additional static meshes embedded in the design. Always present; may be empty.
}

