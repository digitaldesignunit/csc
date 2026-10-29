'use client'

/**
 * Who performed the work (`performed_by`, spec 3.3.1): the signed-in recorder
 * in one tap ("Add me"), laboratories and other people by typing. "Add me"
 * copies the profile (name, organisation, ROR, website, ORCID; decision 8.133 d)
 * into the actor, so the record states where they worked then; the role is the
 * profile's default role. "Add my organisation" adds the organisation of the
 * profile as a performer of its own. The actor fields and their "?" texts are the
 * backend's.
 */
import { useState } from 'react'
import Link from 'next/link'
import { Building2, ChevronDown, Plus, Trash2, UserCheck } from 'lucide-react'

import SchemaFields from '@/components/evidence/SchemaFields'
import { Button } from '@/components/ui/button'
import type { Me } from '@/generated/AccessModels'
import type { JsonSchema } from '@/lib/evidence/api'
import type { MethodLayout } from '@/lib/evidence/layout'
import { emptyObject, resolve, type FormObject, type FormValue } from '@/lib/evidence/schema'
import { actorFromProfile, hasOrganization, isMyOrganization, organizationFromProfile } from '@/lib/profile'
import { cn } from '@/lib/utils'

const NO_LAYOUT: MethodLayout = {
  fanOut: 'single', recordLabel: 'actor', shared: [], blankOnRepeat: [], dateFields: [], flexDateFields: [],
  longText: [], timestampFields: [],
}

export function isMe(actor: FormObject, me: Me | null): boolean {
  return !!me && actor.kind === 'user' && actor.user_id === me._id
}

/** The actor "Add me" makes: the profile copied into the form's own shape. */
export function meActor(me: Me, root: JsonSchema): FormObject {
  const actorSchema = resolve({ $ref: '#/$defs/Actor' }, root).schema
  const copy = actorFromProfile(me) as Record<string, FormValue>
  return { ...emptyObject(actorSchema, root), ...copy }
}

/** The actor "Add my organisation" makes: the organisation of the profile in the form's own shape. */
export function organizationActor(me: Me, root: JsonSchema): FormObject | null {
  const copy = organizationFromProfile(me) as Record<string, FormValue> | null
  if (!copy) return null
  const actorSchema = resolve({ $ref: '#/$defs/Actor' }, root).schema
  return { ...emptyObject(actorSchema, root), ...copy }
}

function summaryOf(actor: FormObject): string {
  const text = (key: string) => (typeof actor[key] === 'string' ? (actor[key] as string).trim() : '')
  return [text('name'), text('organization'), text('orcid') ? `ORCID ${text('orcid')}` : ''].filter(Boolean).join(', ')
}

export default function ActorsField({
  actors,
  onChange,
  root,
  me,
  errors,
  idPrefix,
}: {
  actors: FormObject[]
  onChange: (next: FormObject[]) => void
  /** a payload schema that defines `Actor` */
  root: JsonSchema
  me: Me | null
  errors?: Record<string, string[]>
  idPrefix: string
}) {
  const actorSchema = resolve({ $ref: '#/$defs/Actor' }, root).schema
  const meListed = actors.some((a) => isMe(a, me))
  const [details, setDetails] = useState<number | null>(null)
  const profileThin = !!me && !me.organization && !me.orcid

  const addMe = () => {
    if (!me) return
    onChange([...actors, meActor(me, root)])
  }
  const orgListed = actors.some((a) => isMyOrganization(a, me))
  const addOrganization = () => {
    const actor = me ? organizationActor(me, root) : null
    if (actor) onChange([...actors, actor])
  }
  const addOther = () => {
    onChange([...actors, { ...emptyObject(actorSchema, root), kind: 'organization' }])
  }

  return (
    <div className="space-y-3">
      {actors.map((actor, index) => {
        const mine = isMe(actor, me)
        const set = (next: FormObject) => onChange(actors.map((a, i) => (i === index ? next : a)))
        return (
          <fieldset key={index} className="space-y-3 rounded-md border border-border/70 bg-background p-3">
            <legend className="flex items-center gap-1 px-1 text-xs font-semibold text-muted-foreground">
              {mine ? <><UserCheck className="h-3.5 w-3.5" />You</> : `Performer ${index + 1}`}
            </legend>
            {mine ? (
              <>
                <p className="text-sm">{summaryOf(actor) || 'You'}</p>
                <SchemaFields
                  schema={actorSchema} root={root} value={actor} onChange={set}
                  idPrefix={`${idPrefix}-${index}`} layout={NO_LAYOUT} errors={errors} only={['role']}
                />
                <button
                  type="button"
                  aria-expanded={details === index}
                  onClick={() => setDetails(details === index ? null : index)}
                  className="flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:underline"
                >
                  <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', details !== index && '-rotate-90')} />
                  Details copied from your profile
                </button>
                {details === index && (
                  <SchemaFields
                    schema={actorSchema} root={root} value={actor} onChange={set}
                    idPrefix={`${idPrefix}-${index}-d`} layout={NO_LAYOUT} errors={errors}
                    hide={['kind', 'user_id', 'redacted_at', 'email', 'role', 'accreditation']}
                  />
                )}
              </>
            ) : (
              <SchemaFields
                schema={actorSchema} root={root} value={actor} onChange={set}
                idPrefix={`${idPrefix}-${index}`} layout={NO_LAYOUT} errors={errors}
                hide={['user_id', 'redacted_at', 'email']}
              />
            )}
            <Button
              type="button" variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
              onClick={() => onChange(actors.filter((_, i) => i !== index))}
            >
              <Trash2 className="mr-1 h-3 w-3" />Remove
            </Button>
          </fieldset>
        )
      })}
      <div className="flex flex-wrap items-center gap-2">
        {me && !meListed && (
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={addMe}>
            <UserCheck className="mr-1 h-3.5 w-3.5" />Add me (I performed this)
          </Button>
        )}
        {hasOrganization(me) && !orgListed && (
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={addOrganization}>
            <Building2 className="mr-1 h-3.5 w-3.5" />Add my organisation
          </Button>
        )}
        <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={addOther}>
          <Plus className="mr-1 h-3.5 w-3.5" />Laboratory or other person
        </Button>
      </div>
      {profileThin && (
        <p className="text-xs text-muted-foreground">
          Your profile has no organisation or ORCID yet:{' '}
          <Link href="/settings" className="underline underline-offset-2">add them in Settings</Link>{' '}
          and &quot;Add me&quot; fills them in.
        </p>
      )}
    </div>
  )
}
