// Auto-generated from backend OpenAPI schema
// Generated on: 2026-10-02T21:09:59.038Z
// Source: http://127.0.0.1:8011/schema/evidence
import type { Actor, StatusChange } from './CatalogModels';
import type { Tombstone } from './AccessModels';

export interface Attachment {
  index: number;
  name: string;
  media_type: string;
  size: number;
  sha256: string;
  uploaded_by_user_id: string;
  uploaded_at: string;
  removed?: AttachmentRemoval | null;
}

export interface AttachmentRemoval {
  at: string;
  by_user_id: string;
  reason: string;
}

export interface ContextView {
  snapshot_id?: string | null;
  resolution: string;
}

export interface DerivationModel {
  kind: string;
  reference?: string | null;
  note?: string | null;
}

export interface DerivedResult {
  quantity: string;
  value?: number | number | string | null;
  range?: (number | number | string)[] | null;
  unit?: string | null;
  kind?: string;
  model: DerivationModel;
}

export interface EvidenceView {
  _id: string;
  identity_id: string;
  method: 'rebound_hammer' | 'core_compression' | 'archival_document' | 'visual_inspection' | 'era_heuristic' | 'manufacturer_datasheet' | 'reinforcement_layout';
  method_version?: number;
  source_tier: 'destructive' | 'ndt' | 'archival' | 'visual' | 'heuristic';
  standard?: Standard | null;
  observed_at: string;
  observed_at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown';
  sampled_at?: string | null;
  sampled_at_precision?: 'exact' | 'day' | 'month' | 'year' | 'unknown' | null;
  performed_by?: Actor[];
  recorded_by_user_id: string;
  recorded_by_username?: string | null;
  position: Position;
  summary: Summary;
  derived?: DerivedResult[];
  payload?: Record<string, unknown>;
  destructive?: boolean;
  attachments?: Attachment[];
  notes?: string | null;
  status: 'draft' | 'pending' | 'published' | 'rejected' | 'withdrawn';
  status_changed_by_user_id?: string | null;
  status_changed_at?: string | null;
  status_history?: StatusChange[];
  verification?: Verification;
  supersedes?: string | null;
  superseded_by?: string | null;
  etag?: string | null;
  created: string;
  lastmodified: string;
  warnings?: string[];
  context?: ContextView | null;
}

export interface PendingEvidenceItem {
  id: string;
  identity_id: string;
  method: string;
  status: string;
  observed_at: string;
  quantity: string;
  verification_state: 'unverified' | 'self_attested' | 'reviewed' | 'accredited';
  created: string;
  supersedes?: string | null;
  recorded_by_username?: string | null;
  catalog_number?: number | null;
  original_function?: string | null;
  material?: string | null;
  dataset?: string | null;
  identity_published?: boolean;
  pending_snapshot_id?: string | null;
}

export interface Position {
  kind?: 'point' | 'region' | 'face' | 'none';
  snapshot_id?: string | null;
  point?: number[] | null;
  description?: string | null;
}

export interface PropertiesView {
  identity_id: string;
  as_of?: string | null;
  properties: Record<string, unknown>;
  outranked_evidence_ids: Record<string, unknown>;
}

export interface Standard {
  code: string;
  year?: number | null;
}

export interface Summary {
  quantity: string;
  value?: number | number | string | null;
  range?: (number | number | string)[] | null;
  unit?: string | null;
  unit_entered?: string | null;
  kind: 'measured' | 'claimed';
  uncertainty?: Uncertainty | null;
}

export interface Uncertainty {
  type: 'stddev' | 'expanded' | 'range' | 'none';
  value?: number | null;
  k?: number | null;
}

export interface Verification {
  state?: 'unverified' | 'self_attested' | 'reviewed' | 'accredited';
  by?: Actor | null;
  at?: string | null;
  note?: string | null;
}

export interface EvidenceTypesEnvelope {
  evidence: EvidenceView;
  properties: PropertiesView;
  pending: PendingEvidenceItem;
  tombstone: Tombstone;
}

