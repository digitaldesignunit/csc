// Auto-generated from backend OpenAPI schema
// Generated on: 2026-09-30T14:46:19.301Z
// Source: http://127.0.0.1:8000/schema/snapshot-summary

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
}

