// Auto-generated from backend OpenAPI schema
// Generated on: 2026-06-10T12:31:17.123Z
// Source: https://api.ddu.uber.space/schema/snapshot-summary

export interface SnapshotSummaryItem {
  _id: string;
  identity_id: string;
  version: number;
  validated: boolean;
  virtual?: boolean;
  is_current: boolean;
  name?: string | unknown;
  created: string;
  lastmodified: string;
}


export interface PendingValidationSnapshotItem {
  _id: string;
  identity_id: string;
  version: number;
  validated?: boolean;
  is_current: boolean;
  name?: string | unknown;
  created: string;
  catalog_number?: number | unknown;
  type?: string | unknown;
  material?: string | unknown;
  live_version?: number | unknown; // Version of the identity current (live) snapshot, if any
}

