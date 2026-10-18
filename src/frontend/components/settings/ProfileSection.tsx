'use client'

import { useEffect, useState } from 'react'
import { Loader2, Save, UserCog } from 'lucide-react'
import { toast } from 'sonner'

import { Field, NativeSelect } from '@/components/evidence/controls'
import { WriteButton } from '@/components/ui/write-button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { BackendError, backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'
import {
  ACTOR_ROLES,
  ACTOR_ROLE_LABELS,
  checkOrcid,
  checkRor,
  problemField,
  profileFields,
  profilePatch,
  profileProblems,
  type ProfileFields,
  type ProfileProblems,
} from '@/lib/profile'

/**
 * Settings, "Profile" (decision 8.133 b): the name, organisation, ROR, ORCID
 * and default role that "Add me" in the evidence form, Grasshopper and the
 * server copy into the records you make. There is no profile page: the
 * values appear only through the records they fill.
 */
export default function ProfileSection() {
  const { me, loading, refresh } = useMe()
  const [fields, setFields] = useState<ProfileFields>(() => profileFields(null))
  const [shown, setShown] = useState(false)
  const [problems, setProblems] = useState<ProfileProblems>({})
  const [touched, setTouched] = useState<Partial<Record<keyof ProfileFields, boolean>>>({})
  const [saving, setSaving] = useState(false)
  const [general, setGeneral] = useState<string | null>(null)

  useEffect(() => {
    if (me && !shown) {
      setFields(profileFields(me))
      setShown(true)
    }
  }, [me, shown])

  if (!me) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <UserCog className="h-4 w-4 text-primary" aria-hidden />
            Profile
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          {loading ? 'Loading...' : 'Sign in to edit your profile.'}
        </CardContent>
      </Card>
    )
  }

  const set = (patch: Partial<ProfileFields>, key: keyof ProfileFields) => {
    const next = { ...fields, ...patch }
    setFields(next)
    setGeneral(null)
    // a field is judged as it is typed once it was left; the others wait
    if (touched[key]) setProblems((prev) => ({ ...prev, [key]: profileProblems(next)[key] }))
  }
  const leave = (key: keyof ProfileFields) => {
    setTouched((prev) => ({ ...prev, [key]: true }))
    setProblems((prev) => ({ ...prev, [key]: profileProblems(fields)[key] }))
  }

  const patch = profilePatch(fields, me)
  const changed = Object.keys(patch).length > 0

  const save = async () => {
    const found = profileProblems(fields)
    setProblems(found)
    setTouched({ full_name: true, organization: true, organization_ror: true, orcid: true, default_role: true })
    if (Object.keys(found).length > 0) return
    const body: Record<string, string> = { ...patch }
    // send the normal form: the API stores `https://ror.org/<id>` and `0000-...` itself, the field shows it after
    setSaving(true)
    setGeneral(null)
    try {
      await backendJson('/users/me', { method: 'PATCH', body })
      await refresh()
      setShown(false)
      toast.success('Profile saved. New records take these values; older records keep theirs.')
    } catch (err) {
      const text = err instanceof BackendError ? err.message : 'Could not save the profile'
      const key = problemField(text)
      if (key) setProblems((prev) => ({ ...prev, [key]: text }))
      else setGeneral(text)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <UserCog className="h-4 w-4 text-primary" aria-hidden />
          Profile
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">
          &quot;Add me&quot; in the evidence form, Grasshopper and the server copy these values into the records you
          make. A record states where you worked then: a later change never rewrites an older record. Your
          organisation is public, your name and ORCID are shown to signed-in users only.
        </p>
        <form
          className="space-y-3"
          onSubmit={(event) => { event.preventDefault(); void save() }}
          noValidate
        >
          <Field id="profile-name" label="Full name" required errors={problems.full_name ? [problems.full_name] : []}>
            <Input id="profile-name" value={fields.full_name} autoComplete="name" maxLength={200}
              aria-invalid={problems.full_name ? true : undefined}
              onChange={(e) => set({ full_name: e.target.value }, 'full_name')} onBlur={() => leave('full_name')} />
          </Field>
          <Field id="profile-organization" label="Organisation" help="Where you work, e.g. a laboratory, a university or a contractor. Shown publicly with your records."
            errors={problems.organization ? [problems.organization] : []}>
            <Input id="profile-organization" value={fields.organization} autoComplete="organization" maxLength={200}
              aria-invalid={problems.organization ? true : undefined}
              onChange={(e) => set({ organization: e.target.value }, 'organization')} onBlur={() => leave('organization')} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field id="profile-ror" label="ROR of the organisation"
              help="The Research Organization Registry id of your organisation, e.g. 03abcde12 or https://ror.org/03abcde12. Optional."
              errors={problems.organization_ror ? [problems.organization_ror] : []}>
              <Input id="profile-ror" value={fields.organization_ror} placeholder="https://ror.org/..." spellCheck={false}
                aria-invalid={problems.organization_ror ? true : undefined}
                onChange={(e) => set({ organization_ror: e.target.value }, 'organization_ror')} onBlur={() => leave('organization_ror')} />
              <Normalised value={fields.organization_ror} check={checkRor} />
            </Field>
            <Field id="profile-orcid" label="ORCID"
              help="Your ORCID iD, e.g. 0000-0002-1825-0097; the check digit is verified. Optional. Shown to signed-in users only."
              errors={problems.orcid ? [problems.orcid] : []}>
              <Input id="profile-orcid" value={fields.orcid} placeholder="0000-0000-0000-0000" spellCheck={false}
                aria-invalid={problems.orcid ? true : undefined}
                onChange={(e) => set({ orcid: e.target.value }, 'orcid')} onBlur={() => leave('orcid')} />
              <Normalised value={fields.orcid} check={checkOrcid} />
            </Field>
          </div>
          <Field id="profile-role" label="Default role"
            help="The role you have in a record when you add yourself: you can change it in each record.">
            <NativeSelect id="profile-role" value={fields.default_role}
              onChange={(value) => set({ default_role: value as ProfileFields['default_role'] }, 'default_role')}
              options={ACTOR_ROLES.map((role) => ({ value: role, label: ACTOR_ROLE_LABELS[role] }))}
              placeholder={null} className="max-w-56" />
          </Field>
          {general && <p className="text-xs text-destructive" role="alert">{general}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <WriteButton type="submit" disabled={saving || !changed}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              Save the profile
            </WriteButton>
            {!changed && <span className="text-xs text-muted-foreground">Nothing changed.</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

/** The form the API stores, when the typed text is a valid but different spelling. */
function Normalised({ value, check }: { value: string; check: (text: string) => { ok: boolean; value?: string | null } }) {
  const result = check(value)
  if (!result.ok || !result.value || result.value === value.trim()) return null
  return <p className="text-xs text-muted-foreground">Saved as {result.value}</p>
}
