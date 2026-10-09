// Auto-generated from backend OpenAPI schema
// Generated on: 2026-10-06T20:29:26.115Z
// Source: http://127.0.0.1:8791/schema/snapshot-summary

export interface SnapshotSummaryItem {
  _id: string;
  identity_id: string;
  version: number;
  status: 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn';
  is_current: boolean;
  name?: string | null;
  effective_from: string;
  effective_from_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  supersedes?: string | null;
  superseded_by?: string | null;
  added_by_user_id?: string | null;
  added_by_username?: string | null;
  status_changed_at?: string | null;
  geometry_failed?: boolean;
  created: string;
  lastmodified: string;
}


export interface PendingSnapshotItem {
  _id: string;
  identity_id: string;
  version: number;
  status: 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn';
  is_current: boolean;
  name?: string | null;
  created: string;
  catalog_number?: number | null;
  original_function?: string | null;
  material?: string | null;
  dataset?: string | null;
  live_version?: number | null; // Version of the identity's current snapshot, if any
  supersedes?: string | null; // set when this corrects a published one
  added_by_username?: string | null;
}


export interface MySnapshotItem {
  _id: string;
  identity_id: string;
  version: number;
  status: 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn';
  is_current: boolean;
  name?: string | null;
  created: string;
  status_changed_at?: string | null;
  catalog_number?: number | null;
  original_function?: string | null;
  material?: string | null;
  dataset?: string | null;
  supersedes?: string | null; // set when this corrects a published one
  rejection_reason?: string | null; // the moderator's reason, when rejected
}

