import { PackagePlus } from 'lucide-react'

import AddComponentEntry from '@/components/snapshot/AddComponentEntry'
import { uuidFromScan } from '@/lib/scanIds'

/**
 * Adding a component (spec 7.6): the snapshot form in its new-component or
 * cut mode. A scanned unused tag arrives here as `?id=<uuid>` (spec 7.5);
 * `?mode=cut` starts a cut, `?parent=<uuid>` names a parent to start with.
 */
export default async function AddComponentPage({
  searchParams,
}: {
  searchParams: Promise<{ id?: string; mode?: string; parent?: string | string[] }>
}) {
  const { id, mode, parent } = await searchParams
  const tag = typeof id === 'string' ? uuidFromScan(id) ?? undefined : undefined
  const parents = (Array.isArray(parent) ? parent : parent ? [parent] : [])
    .map((p) => uuidFromScan(p))
    .filter((p): p is string => !!p)
  const initialMode = mode === 'cut' || parents.length > 0 ? 'cut' : mode === 'new' || tag ? 'new' : null
  return (
    <div className="container mx-auto max-w-3xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div className="flex items-center gap-2 sm:gap-3">
        <PackagePlus className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold sm:text-2xl">Add component</h1>
      </div>
      <AddComponentEntry tag={tag} parents={parents} initialMode={initialMode} />
    </div>
  )
}
