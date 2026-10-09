import { notFound } from 'next/navigation'
import { History } from 'lucide-react'

import SnapshotForm from '@/components/snapshot/SnapshotForm'
import { MODE_TITLES } from '@/lib/snapshotForm'
import { uuidFromScan } from '@/lib/scanIds'

/**
 * The snapshot form of an existing component (spec 7.6): `?mode=state`
 * records a new state, `?mode=correct&snapshot=<id>` corrects a published
 * version (decisions 7.5, 8.87).
 */
export default async function NewSnapshotPage({
  params,
  searchParams,
}: {
  params: Promise<{ component_id: string }>
  searchParams: Promise<{ mode?: string; snapshot?: string }>
}) {
  const { component_id } = await params
  const { mode, snapshot } = await searchParams
  const identityId = uuidFromScan(component_id)
  if (!identityId) notFound()
  if (mode === 'correct') {
    const snapshotId = typeof snapshot === 'string' ? uuidFromScan(snapshot) : null
    if (!snapshotId) notFound()
    return <Shell mode="correct"><SnapshotForm mode="correct" identityId={identityId} snapshotId={snapshotId} /></Shell>
  }
  return <Shell mode="state"><SnapshotForm mode="state" identityId={identityId} /></Shell>
}

function Shell({ mode, children }: { mode: 'state' | 'correct'; children: React.ReactNode }) {
  return (
    <div className="container mx-auto max-w-3xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div className="flex items-center gap-2 sm:gap-3">
        <History className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold sm:text-2xl">{MODE_TITLES[mode]}</h1>
      </div>
      {children}
    </div>
  )
}
