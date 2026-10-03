'use client'

/**
 * Who performed the work (`performed_by`, spec 3.3.1): the signed-in
 * recorder in one tap ("I performed this"), laboratories and other people
 * by typing. The actor fields and their "?" texts are the backend's.
 */
import { Plus, Trash2, UserCheck } from 'lucide-react'

import SchemaFields from '@/components/evidence/SchemaFields'
import { Button } from '@/components/ui/button'
import type { Me } from '@/generated/AccessModels'
import type { JsonSchema } from '@/lib/evidence/api'
import type { MethodLayout } from '@/lib/evidence/layout'
import { emptyObject, resolve, type FormObject } from '@/lib/evidence/schema'

const NO_LAYOUT: MethodLayout = {
  fanOut: 'single', recordLabel: 'actor', shared: [], blankOnRepeat: [], dateFields: [], longText: [], timestampFields: [],
}

export function isMe(actor: FormObject, me: Me | null): boolean {
  return !!me && actor.kind === 'user' && actor.user_id === me._id
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

  const addMe = () => {
    if (!me) return
    onChange([...actors, {
      ...emptyObject(actorSchema, root),
      kind: 'user', user_id: me._id, name: me.full_name || me.username, role: 'operator',
    }])
  }
  const addOther = () => {
    onChange([...actors, { ...emptyObject(actorSchema, root), kind: 'organization' }])
  }

  return (
    <div className="space-y-3">
      {actors.map((actor, index) => (
        <fieldset key={index} className="space-y-3 rounded-md border border-border/70 p-3">
          <legend className="flex items-center gap-1 px-1 text-xs font-semibold text-muted-foreground">
            {isMe(actor, me) ? <><UserCheck className="h-3.5 w-3.5" />You</> : `Performer ${index + 1}`}
          </legend>
          {isMe(actor, me) ? (
            <SchemaFields
              schema={actorSchema}
              root={root}
              value={actor}
              onChange={(next) => onChange(actors.map((a, i) => (i === index ? next : a)))}
              idPrefix={`${idPrefix}-${index}`}
              layout={NO_LAYOUT}
              errors={errors}
              only={['role']}
            />
          ) : (
            <SchemaFields
              schema={actorSchema}
              root={root}
              value={actor}
              onChange={(next) => onChange(actors.map((a, i) => (i === index ? next : a)))}
              idPrefix={`${idPrefix}-${index}`}
              layout={NO_LAYOUT}
              errors={errors}
              hide={['user_id', 'redacted_at', 'email']}
            />
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground"
            onClick={() => onChange(actors.filter((_, i) => i !== index))}
          >
            <Trash2 className="mr-1 h-3 w-3" />Remove
          </Button>
        </fieldset>
      ))}
      <div className="flex flex-wrap gap-2">
        {me && !meListed && (
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={addMe}>
            <UserCheck className="mr-1 h-3.5 w-3.5" />I performed this
          </Button>
        )}
        <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={addOther}>
          <Plus className="mr-1 h-3.5 w-3.5" />Laboratory or other person
        </Button>
      </div>
    </div>
  )
}
