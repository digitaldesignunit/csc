'use client'

/**
 * What is known about the element (spec 4.4; decision 8.118): the folded
 * properties with the condition grade first, then the other quantities. "Add
 * evidence" is on the evidence records card; here an empty card only shows a
 * quiet link to it, for a user who may add evidence (T11b).
 */
import { FlaskConical } from 'lucide-react'

import PropertiesCard from '@/components/evidence/PropertiesCard'
import Help from '@/components/ui/help'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { canAddEvidence } from '@/lib/componentDetail'
import { conditionBadge } from '@/lib/evidence/format'
import { useMe } from '@/lib/me'
import { addEvidenceHref } from '@/lib/propertiesEmpty'
import { conditionLabel } from '../componentDetailShared'
import { useEvidenceData } from './EvidenceData'

/** What the "?" of the heading says: the properties are not typed in (the Data Model page, rule 2 and the fold). */
const PROPERTIES_HELP =
  'Properties are values the catalog works out from the published evidence records of this element. '
  + 'For each quantity the most trusted kind of source wins. They are not typed in: to change one, add evidence.'

export default function ComponentPropertiesCard({ catalog }: { catalog: CatalogComponent }) {
  const { identity } = catalog
  const identityId = String(identity._id ?? '')
  const snapshot = primarySnapshot(catalog)
  const { records } = useEvidenceData()
  const { me, isAdmin, rolesIn } = useMe()
  const mayAdd = canAddEvidence({
    signedIn: !!me, isAdmin, roles: identity.dataset ? rolesIn(identity.dataset) : [],
    withdrawn: identity.withdrawn, currentSnapshotId: identity.current_snapshot_id,
  })
  const condition = conditionBadge(snapshot.properties)
  const version = typeof snapshot.version === 'number' ? `This version (v${snapshot.version})` : 'This version'

  return (
    <section id="properties" aria-label="Properties" className="scroll-mt-4 rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="mb-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FlaskConical className="h-4 w-4" />Properties
          <Help label="Properties" text={PROPERTIES_HELP} />
        </h2>
      </div>
      <div className="space-y-3">
        <PropertiesCard
          headless
          addEvidenceHref={addEvidenceHref(identityId, mayAdd)}
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
