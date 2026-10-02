// Auto-generated from backend OpenAPI schema
// Generated on: 2026-10-02T13:41:52.769Z
// Source: http://127.0.0.1:8000/schema/lineage

export interface ChangeLogEntryView {
  _id: string;
  record_kind: string;
  record_id: string;
  identity_id: string;
  at: string;
  by_user_id?: string | null;
  cause: 'patch' | 'inherited_from_parent' | 'material_merge' | 'exit' | 'reenter' | 'withdraw' | 'reinstate' | 'migration' | 'derived_exit';
  source_record_id?: string | null;
  changes: FieldChange[];
  by_username?: string | null;
}

export interface FieldChange {
  path: string;
  old?: unknown;
  new?: unknown;
}

export interface Material {
  _id: string;
  label: string;
  group: 'mineral' | 'metal' | 'bio-based' | 'polymer' | 'bituminous' | 'insulation' | 'other';
  default_class: string;
  uniclass?: string | null;
  notes?: string | null;
  retired?: boolean;
  merged_into?: string | null;
}

export interface LineageTypesEnvelope {
  change: ChangeLogEntryView;
  material: Material;
}

