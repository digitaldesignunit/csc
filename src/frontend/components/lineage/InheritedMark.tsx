import Link from 'next/link'
import { CornerLeftUp } from 'lucide-react'

import type { ComponentIdentity } from '@/generated/CatalogModels'
import type { InheritUnit } from '@/generated/Vocab'

/**
 * Marks a value a child takes over from its parents (spec section 3.1.2,
 * I17): it changes when the parent's does. Links to the parent it came from.
 */
export default function InheritedMark({ identity, unit }: {
  identity: Pick<ComponentIdentity, 'inherited_fields' | 'inherited_from' | 'parent_identities'>
  unit: InheritUnit
}) {
  if (!(identity.inherited_fields ?? []).includes(unit)) return null
  const from = identity.inherited_from ?? identity.parent_identities?.[0]
  const merged = (identity.parent_identities ?? []).length > 1
  const title = merged ? 'Taken over from the parents (they agree)' : 'Taken over from the parent'
  const mark = (
    <span className="inline-flex items-center gap-0.5 rounded border border-sky-300 bg-sky-50 px-1 text-[10px] font-medium text-sky-800 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-200">
      <CornerLeftUp className="h-2.5 w-2.5" aria-hidden="true" />
      inherited
    </span>
  )
  return from ? (
    <Link href={`/components/${encodeURIComponent(from)}`} title={title} className="ml-1 align-middle">
      {mark}
    </Link>
  ) : (
    <span title={title} className="ml-1 align-middle">{mark}</span>
  )
}
