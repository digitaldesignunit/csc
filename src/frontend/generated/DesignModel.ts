// Auto-generated from backend OpenAPI schema
// Generated on: 2025-01-15T10:30:00.000Z
// Source: https://api.ddu.uber.space/schema/design

export interface DesignInsertionFrame {
  o: number[]; // Origin point as [x, y, z] coordinates
  x: number[]; // X-axis vector as [x, y, z] coordinates
  y: number[]; // Y-axis vector as [x, y, z] coordinates
  z: number[]; // Z-axis vector as [x, y, z] coordinates
}

export interface DesignComponent {
  component: string; // Component ID (GUID) reference
  iframe: DesignInsertionFrame; // Insertion frame defining component orientation
}

export interface DesignModel {
  _id?: string; // Globally unique design identifier (GUID)
  id?: string; // Globally unique design identifier (GUID) - alias for _id
  name?: string; // Human readable design name (optional)
  description?: string; // Design description (optional)
  creator: string; // UUID of user who created this design
  creator_username?: string; // Username of creator (enriched field)
  created: string; // ISO timestamp when design was created
  lastmodified: string; // ISO timestamp when design was last modified
  components: DesignComponent[]; // List of components and their insertion frames
}

export interface CreateDesignRequest {
  name?: string; // Human readable design name (optional)
  description?: string; // Design description (optional)
  components: DesignComponent[]; // List of components and their insertion frames
}

export interface UpdateDesignRequest {
  name?: string; // Human readable design name (optional)
  description?: string; // Design description (optional)
  components?: DesignComponent[]; // List of components and their insertion frames
}

// Helper type for design list items (with pagination)
export interface DesignListItem extends Omit<DesignModel, 'components'> {
  component_count: number; // Number of components in the design
}

// Helper type for design creation response
export interface CreateDesignResponse extends DesignModel {
  message?: string; // Success message
}

// Helper type for design update response
export interface UpdateDesignResponse extends DesignModel {
  message?: string; // Success message
}

// Helper type for design deletion response
export interface DeleteDesignResponse {
  message: string; // Success message
}
