// Auto-generated from backend OpenAPI schema
// Generated on: 2025-10-14T12:28:56.169Z
// Source: https://api.ddu.uber.space/schema/design

export interface ComponentExtrusion {
  profile: ComponentPolylinePoints; // Extrusion profile points
  height: number; // Extrusion height
}

export interface ComponentGeometry {
  mesh?: ComponentMesh | unknown; // Mesh geometry (single mesh - backward compat)
  meshes?: ComponentMesh[] | unknown; // Array of mesh geometries (multiple meshes)
  extrusion?: ComponentExtrusion | unknown; // Extrusion geometry
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


export interface DesignAdditionalGeometry {
  id?: string; // Globally unique identifier for this additional geometry item
  name?: string | unknown; // Optional human-readable name
  iframe: DesignInsertionFrame; // Insertion frame defining geometry orientation
  geometry: ComponentGeometry; // Geometry data. Use 'meshes' array; if single mesh, provide array with one entry.
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

