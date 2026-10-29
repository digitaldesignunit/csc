'use client'

/**
 * "Add evidence" (the evidence form of the element) on the evidence records
 * card (8.118 Q1, amended in 0.6.4.2). The empty Properties card links to the
 * same form under the same condition (`canAddEvidence`, `addEvidenceHref`).
 */
import Link from 'next/link'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { canAddEvidence } from '@/lib/componentDetail'
import { useMe } from '@/lib/me'
import { addEvidenceHref } from '@/lib/propertiesEmpty'

export default function AddEvidenceButton({
  identityId,
  dataset,
  withdrawn,
  currentSnapshotId,
}: {
  identityId: string
  dataset?: string | null
  withdrawn?: unknown
  currentSnapshotId?: string | null
}) {
  const { me, isAdmin, rolesIn } = useMe()
  const href = addEvidenceHref(identityId,
    canAddEvidence({ signedIn: !!me, isAdmin, roles: dataset ? rolesIn(dataset) : [], withdrawn, currentSnapshotId }))
  if (!href) return null
  return (
    <Button asChild size="sm" className="h-7 text-xs">
      <Link href={href}>
        <Plus className="mr-1 h-3.5 w-3.5" />Add evidence
      </Link>
    </Button>
  )
}
