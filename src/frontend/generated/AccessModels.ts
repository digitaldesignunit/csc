// Auto-generated from backend OpenAPI schema
// Generated on: 2026-10-02T21:09:59.002Z
// Source: http://127.0.0.1:8011/schema/access

export interface AdminUserRow {
  _id: string;
  username: string;
  email?: string | null;
  full_name?: string | null;
  disabled?: boolean | null;
  role?: 'user' | 'admin';
  email_verified?: boolean;
  memberships?: MembershipRow[];
  invited?: boolean;
}

export interface DatasetMemberView {
  user_id: string;
  username?: string | null;
  full_name?: string | null;
  email?: string | null;
  roles: ('contributor' | 'reviewer' | 'moderator')[];
  added_at?: string | null;
}

export interface DatasetView {
  _id: string;
  name: string;
  description?: string | null;
  visibility: 'members' | 'catalog';
  roles: ('contributor' | 'reviewer' | 'moderator')[];
  members?: DatasetMemberView[] | null;
}

export interface InvitationView {
  _id: string;
  email: string;
  dataset?: string | null;
  roles: ('contributor' | 'reviewer' | 'moderator')[];
  created_by_user_id: string;
  created: string;
  expires_at: string;
  used_at?: string | null;
  used_by_user_id?: string | null;
  revoked_at?: string | null;
  state: 'open' | 'used' | 'expired' | 'revoked';
}

export interface InviteResult {
  email: string;
  result: 'invited' | 'exists';
  invitation?: InvitationView | null;
}

export interface Me {
  _id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
  role: string;
  memberships: Membership[];
  moderated_datasets: string[];
}

export interface MemberByEmailResult {
  email: string;
  result: 'added' | 'invited';
  user_id?: string | null;
  invitation?: InvitationView | null;
}

export interface Membership {
  dataset: string;
  name: string;
  visibility: 'members' | 'catalog';
  roles: ('contributor' | 'reviewer' | 'moderator')[];
}

export interface MembershipRow {
  dataset: string;
  roles: ('contributor' | 'reviewer' | 'moderator')[];
}

export interface Tombstone {
  _id: string;
  kind: 'identity' | 'snapshot' | 'evidence';
  status: string;
  withdrawn_at?: string | null;
  version?: number | null;
  catalog_number?: number | null;
  identity_id?: string | null;
  current_snapshot_id?: string | null;
  duplicate_of?: string | null;
}

export interface UserHit {
  _id: string;
  username: string;
  full_name?: string | null;
  email?: string | null;
}

export interface AccessTypesEnvelope {
  me: Me;
  dataset: DatasetView;
  tombstone: Tombstone;
  invitation: InvitationView;
  invite_result: InviteResult;
  member_result: MemberByEmailResult;
  admin_user: AdminUserRow;
  user_hit: UserHit;
}

