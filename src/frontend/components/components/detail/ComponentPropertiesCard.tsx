'use client'

/**
 * What is known about the piece (spec 4.4; decision 8.118): the folded
 * properties with the condition grade first, then the other quantities. It is
 * the top of the old Evidence card, with "Add evidence" kept visible here
 * where the gap is seen.
 */
import Link from 'next/link'
import { FlaskConical, Plus } from 'lucide-react'

import PropertiesCard from '@/components/evidence/PropertiesCard'
import { Button } from '@/components/ui/button'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { conditionBadge } from '@/lib/evidence/format'
import { useMe } from '@/lib/me'
import { conditionLabel } from '../componentDetailShared'
import { useEvidenceData } from './EvidenceData'

export default function ComponentPropertiesCard({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const identityId = String(identity._id ?? '')
  const snapshot = primarySnapshot(catalog)
  const { me, isAdmin, rolesIn } = useMe()
  const { records } = useEvidenceData()
  const canRecord = !!me && (isAdmin || rolesIn(identity.dataset).includes('contributor'))
    && !identity.withdrawn && !!identity.current_snapshot_id
  const condition = conditionBadge(snapshot.properties)
  const version = typeof snapshot.version === 'number' ? `This version (v${snapshot.version})` : 'This version'

  return (
    <section id="properties" aria-label="Properties" className="scroll-mt-4 rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical className="h-4 w-4" />Properties
        </h2>
        {canRecord && (
          <Button asChild size="sm" className="h-7 text-xs">
            <Link href={`/components/${encodeURIComponent(identityId)}/evidence/new`}>
              <Plus className="mr-1 h-3.5 w-3.5" />Add evidence
            </Link>
          </Button>
        )}
      </div>
      <div className="space-y-3">
        <PropertiesCard
          headless
          identityId={identityId}
          properties={identity.properties}
          versionProperties={snapshot.properties}
          versionLabel={version}
          records={records ?? []}
          conditionDerived={condition.basis === 'findings' && condition.grade !== null
            ? { grade: condition.grade, label: conditionLabel(condition.grade) }
            : null}
        />
      </div>
    </section>
  )
}
