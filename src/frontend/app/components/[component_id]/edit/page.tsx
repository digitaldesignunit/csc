import { notFound } from 'next/navigation'
import { Pencil } from 'lucide-react'

import EditSnapshotForm from '@/components/snapshot/EditSnapshotForm'
import { uuidFromScan } from '@/lib/scanIds'

/**
 * Edit the details of any version (spec 3.2.2, plan P7, decision 8.123 c):
 * name, notes, location, colour, the date it is valid from, the capture
 * notes and the capture fields that are still empty. `?snapshot=<sid>` picks
 * the version, the current one by default. The backend decides per field who
 * may.
 */
export default async function ComponentEditPage({
  params,
  searchParams,
}: {
  params: Promise<{ component_id: string }>
  searchParams: Promise<{ snapshot?: string }>
}) {
  const { component_id } = await params
  const { snapshot } = await searchParams
  const id = uuidFromScan(component_id)
  if (!id) notFound()
  return (
    <div className="container mx-auto max-w-3xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div className="flex items-center gap-2 sm:gap-3">
        <Pencil className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold sm:text-2xl">Edit details</h1>
      </div>
      <EditSnapshotForm identityId={id} snapshotId={snapshot ?? null} />
    </div>
  )
}
