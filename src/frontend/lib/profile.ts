/**
 * The personal profile (decision 8.133): the checks the Settings form makes
 * before it asks the API (the same rules as `apps/catalog/profile.py`, so a
 * mistake is named at the field), and the actor the profile makes.
 *
 * Run: npm test
 */

export const ACTOR_ROLES = ['operator', 'supervisor', 'laboratory', 'client', 'witness'] as const
export type ActorRole = (typeof ACTOR_ROLES)[number]

export const ACTOR_ROLE_LABELS: Record<ActorRole, string> = {
  operator: 'Operator',
  supervisor: 'Supervisor',
  laboratory: 'Laboratory',
  client: 'Client',
  witness: 'Witness',
}

/** The role a profile gives the actor when nothing else is chosen. */
export function roleOf(value: string | null | undefined): ActorRole {
  return (ACTOR_ROLES as readonly string[]).includes(value ?? '') ? (value as ActorRole) : 'operator'
}

const ORCID_URL = /^https?:\/\/orcid\.org\//i
const ROR_URL = /^https?:\/\/ror\.org\//i
const ROR_ID = /^0[a-hj-km-np-tv-z0-9]{6}[0-9]{2}$/
const ORCID_ID = /^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$/

/** The ISO 7064 MOD 11-2 check character of the first 15 digits. */
export function orcidCheckDigit(digits: string): string {
  let total = 0
  for (const char of digits) total = (total + Number(char)) * 2
  const result = (12 - (total % 11)) % 11
  return result === 10 ? 'X' : String(result)
}

export type Checked = { ok: true; value: string | null } | { ok: false; message: string }

/** `0000-0002-1825-0097` from the bare id, the id without hyphens or the orcid.org URL; empty is fine. */
export function checkOrcid(input: string): Checked {
  let text = input.trim()
  if (!text) return { ok: true, value: null }
  text = text.replace(ORCID_URL, '').replace(/ /g, '').toUpperCase()
  if (/^\d{15}[\dX]$/.test(text)) text = text.replace(/(.{4})(?=.)/g, '$1-')
  if (!ORCID_ID.test(text)) return { ok: false, message: 'An ORCID looks like 0000-0002-1825-0097.' }
  const digits = text.replace(/-/g, '')
  if (orcidCheckDigit(digits.slice(0, 15)) !== digits[15]) {
    return { ok: false, message: 'This ORCID has a wrong check digit.' }
  }
  return { ok: true, value: text }
}

/** `https://ror.org/<id>` from the bare id or the URL; empty is fine. */
export function checkRor(input: string): Checked {
  const text = input.trim()
  if (!text) return { ok: true, value: null }
  const id = text.replace(ROR_URL, '').replace(/^\/+|\/+$/g, '').toLowerCase()
  if (!ROR_ID.test(id)) {
    return { ok: false, message: 'A ROR id looks like 03abcde12 (https://ror.org/...).' }
  }
  return { ok: true, value: `https://ror.org/${id}` }
}

/** The web page of the organisation: http or https only, as `Actor.url`; empty is fine. */
export function checkUrl(input: string): Checked {
  const text = input.trim()
  if (!text) return { ok: true, value: null }
  if (!/^https?:\/\//i.test(text)) return { ok: false, message: 'The website must start with http:// or https://.' }
  if (text.length > 500) return { ok: false, message: 'At most 500 characters.' }
  return { ok: true, value: text }
}

export type ProfileFields = {
  full_name: string
  organization: string
  organization_ror: string
  organization_url: string
  orcid: string
  default_role: ActorRole
}

export type ProfileLike = {
  full_name?: string | null
  organization?: string | null
  organization_ror?: string | null
  organization_url?: string | null
  orcid?: string | null
  default_role?: string | null
}

export function profileFields(me: ProfileLike | null | undefined): ProfileFields {
  return {
    full_name: me?.full_name ?? '',
    organization: me?.organization ?? '',
    organization_ror: me?.organization_ror ?? '',
    organization_url: me?.organization_url ?? '',
    orcid: me?.orcid ?? '',
    default_role: roleOf(me?.default_role),
  }
}

export type ProfileProblems = Partial<Record<keyof ProfileFields, string>>

/** What is wrong with the fields, by field; nothing when the profile can be saved. */
export function profileProblems(fields: ProfileFields): ProfileProblems {
  const problems: ProfileProblems = {}
  if (!fields.full_name.trim()) problems.full_name = 'The name cannot be empty.'
  else if (fields.full_name.trim().length > 200) problems.full_name = 'At most 200 characters.'
  if (fields.organization.trim().length > 200) problems.organization = 'At most 200 characters.'
  const ror = checkRor(fields.organization_ror)
  if (!ror.ok) problems.organization_ror = ror.message
  const url = checkUrl(fields.organization_url)
  if (!url.ok) problems.organization_url = url.message
  const orcid = checkOrcid(fields.orcid)
  if (!orcid.ok) problems.orcid = orcid.message
  return problems
}

/** The body of `PATCH /users/me` for the fields that differ from what is stored. */
export function profilePatch(fields: ProfileFields, stored: ProfileLike | null | undefined): Record<string, string> {
  const before = profileFields(stored)
  const patch: Record<string, string> = {}
  for (const key of Object.keys(fields) as (keyof ProfileFields)[]) {
    if (fields[key].trim() !== before[key].trim()) patch[key] = fields[key].trim()
  }
  return patch
}

/** The text of an API message for one of the profile fields, or null (`an ORCID looks like ...`). */
export function problemField(message: string): keyof ProfileFields | null {
  const text = message.toLowerCase()
  if (text.includes('orcid')) return 'orcid'
  if (text.includes('website')) return 'organization_url'
  if (text.includes('ror')) return 'organization_ror'
  if (text.includes('name')) return 'full_name'
  return null
}

export type ActorLike = Record<string, unknown>

/**
 * The actor a profile makes ("Add me", 8.133 d): the account id as `user_id`,
 * name, organisation, ROR, website and ORCID copied, the default role. A copy:
 * a later change of the profile never rewrites a record.
 */
export function actorFromProfile(me: { _id: string; username: string } & ProfileLike): ActorLike {
  const fields = profileFields(me)
  const actor: ActorLike = {
    kind: 'user',
    user_id: me._id,
    name: fields.full_name.trim() || me.username,
    role: fields.default_role,
  }
  if (fields.organization.trim()) actor.organization = fields.organization.trim()
  if (fields.organization_ror.trim()) actor.organization_ror = fields.organization_ror.trim()
  if (fields.organization_url.trim()) actor.url = fields.organization_url.trim()
  if (fields.orcid.trim()) actor.orcid = fields.orcid.trim()
  return actor
}

/** Whether the profile names an organisation, so that "Add my organisation" has something to add. */
export function hasOrganization(me: ProfileLike | null | undefined): boolean {
  return !!me?.organization?.trim()
}

/**
 * The actor "Add my organisation" makes: the organisation of the profile as a
 * performer of its own (a laboratory, a client): organisation, ROR and website
 * copied, no person, no role (it is chosen in the record). Null when the
 * profile has no organisation.
 */
export function organizationFromProfile(me: ProfileLike | null | undefined): ActorLike | null {
  if (!hasOrganization(me)) return null
  const fields = profileFields(me)
  const actor: ActorLike = { kind: 'organization', organization: fields.organization.trim() }
  if (fields.organization_ror.trim()) actor.organization_ror = fields.organization_ror.trim()
  if (fields.organization_url.trim()) actor.url = fields.organization_url.trim()
  return actor
}

/** Whether a performer is the organisation of the profile (the button is then not offered again). */
export function isMyOrganization(actor: ActorLike, me: ProfileLike | null | undefined): boolean {
  if (actor.kind !== 'organization' || !hasOrganization(me)) return false
  const text = (value: unknown) => (typeof value === 'string' ? value.trim().toLowerCase() : '')
  return text(actor.organization) === text(me?.organization) && !text(actor.name)
}
