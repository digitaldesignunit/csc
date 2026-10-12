'use client'

/**
 * Who did the work of an origin (`origin.performed_by`, spec 3.3.1): the
 * deinstaller, the demolition contractor, the fabricator that produced an
 * offcut. The same actor form as the evidence form (a person, an organisation
 * with its ROR and web page, "Add me" from the profile); the fields and their
 * texts come from the backend's `Actor` schema, which the method registry
 * carries. The parent holds plain actors; blank ones are dropped on the way
 * out, so an empty row never reaches the request.
 */
import { useEffect, useMemo, useState } from 'react'

import ActorsField from '@/components/evidence/form/ActorsField'
import type { Actor } from '@/generated/CatalogModels'
import { actorRootOf, loadMethods, type JsonSchema } from '@/lib/evidence/api'
import { fromPayload, resolve, toPayload, type FormObject } from '@/lib/evidence/schema'
import { useMe } from '@/lib/me'

export function actorsOf(forms: FormObject[], root: JsonSchema): Actor[] {
  const schema = resolve({ $ref: '#/$defs/Actor' }, root).schema
  return forms
    .map((form) => toPayload(schema, form, root) as unknown as Actor)
    .filter((actor) => Object.keys(actor).length > 0 && actor.kind !== undefined)
}

export default function PerformedByField({
  actors,
  onChange,
  idPrefix,
}: {
  /** the actors when the field opens; it keeps its own rows from then on */
  actors: Actor[]
  onChange: (actors: Actor[]) => void
  idPrefix: string
}) {
  const { me } = useMe()
  const [root, setRoot] = useState<JsonSchema | null>(null)
  const [failed, setFailed] = useState(false)
  const [rows, setRows] = useState<FormObject[] | null>(null)

  useEffect(() => {
    let cancelled = false
    loadMethods()
      .then((methods) => { if (!cancelled) setRoot(actorRootOf(methods)) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [])

  const initial = useMemo(() => {
    if (!root) return null
    const schema = resolve({ $ref: '#/$defs/Actor' }, root).schema
    return actors.map((actor) => fromPayload(schema, actor as unknown as Record<string, unknown>, root))
    // the field takes its first value only: later edits are its own
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root])

  const shown = rows ?? initial
  if (failed) return <p className="text-xs text-muted-foreground">The actor form could not be loaded.</p>
  if (!root || !shown) return <p className="text-xs text-muted-foreground">Loading...</p>
  return (
    <ActorsField
      actors={shown}
      onChange={(next) => {
        setRows(next)
        onChange(actorsOf(next, root))
      }}
      root={root}
      me={me}
      idPrefix={idPrefix}
    />
  )
}
