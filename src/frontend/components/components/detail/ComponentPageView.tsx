'use client'

/**
 * The component page (decision 8.118, stage 1): a header strip with the
 * chips and the Actions menu, banners only when they apply, the viewer with
 * its toolbar, the facts, the properties, the provenance, photos and location,
 * the evidence records and the History card.
 *
 * Phone order: header, banners, viewer, facts, properties, provenance, photos
 * and location, records, history. Desktop: two columns --- the facts, the
 * properties and the provenance (about 24 rem) beside the viewer, the photos
 * and location, the records and the history.
 */
import { useSession } from 'next-auth/react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot, type CatalogShallowRow } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import RecordRecentComponent from '@/components/layout/RecordRecentComponent'
import { bannersOf, type Banner } from '@/lib/componentDetail'
import { cn } from '@/lib/utils'
import ComponentViewer from '../ComponentViewer'
import ComponentDetailSnapshotBanner from '../ComponentDetailSnapshotBanner'
import ComponentProvenanceCard from '../ComponentProvenanceCard'
import { geometryFailed } from '../componentDetailShared'
import ComponentFactsCard from './ComponentFactsCard'
import ComponentHeaderStrip from './ComponentHeaderStrip'
import ComponentHistoryCard from './ComponentHistoryCard'
import ComponentPhotosLocationCard from './ComponentPhotosLocationCard'
import ComponentPropertiesCard from './ComponentPropertiesCard'
import ComponentRecordsCard from './ComponentRecordsCard'
import { EvidenceDataProvider } from './EvidenceData'

const BANNER_TONE: Record<Banner['tone'], string> = {
  info: 'border-sky-300 bg-sky-50 text-sky-950 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-100',
  warn: 'border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100',
  bad: 'border-red-300 bg-red-50 text-red-950 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100',
}

export default function ComponentPageView({
  catalog,
  snapshots,
  childIdentities,
  activeSnapshotId,
  viewingVersion,
  liveVersion,
  isViewingLive,
  snapshotStatus,
}: {
  catalog: CatalogComponent
  snapshots: SnapshotSummaryItem[]
  childIdentities: CatalogShallowRow[]
  activeSnapshotId: string
  viewingVersion: number
  liveVersion: number
  isViewingLive: boolean
  snapshotStatus?: string | null
}) {
  const { data: session } = useSession()
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const identityId = String(identity._id ?? '')
  const banners = bannersOf({
    identity: identity as never,
    signedIn: !!session?.user,
    geometryFailed: geometryFailed(snapshot),
  })

  return (
    <EvidenceDataProvider identityId={identityId}>
      <div className="mx-auto w-full max-w-[110rem] space-y-3 p-3 sm:p-4">
        <RecordRecentComponent
          id={identityId}
          label={`#${identity.catalog_number} ${snapshot.name ?? ''}`.trim()}
        />
        <ComponentHeaderStrip catalog={catalog} snapshots={snapshots} />
        {banners.map((banner) => (
          <p key={banner.id} role="status"
            className={cn('rounded-lg border px-3 py-2 text-sm', BANNER_TONE[banner.tone])}>
            {banner.text}
          </p>
        ))}
        {!isViewingLive && (
          <ComponentDetailSnapshotBanner
            identityId={identityId}
            viewingVersion={viewingVersion}
            liveVersion={liveVersion}
            status={snapshotStatus}
          />
        )}

        <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-[minmax(20rem,24rem)_minmax(0,1fr)]">
          <div className="order-1 min-w-0 lg:col-start-2 lg:row-start-1">
            <ComponentViewer catalog={catalog} compactDesktop toolbar />
          </div>
          <div className="contents lg:col-start-1 lg:row-span-4 lg:row-start-1 lg:flex lg:min-w-0 lg:flex-col lg:gap-3">
            <div className="order-2 min-w-0"><ComponentFactsCard catalog={catalog} /></div>
            <div className="order-3 min-w-0"><ComponentPropertiesCard catalog={catalog} /></div>
            <div className="order-4 min-w-0">
              <ComponentProvenanceCard catalog={catalog} childIdentities={childIdentities} />
            </div>
          </div>
          <div className="order-5 min-w-0 lg:col-start-2 lg:row-start-2">
            <ComponentPhotosLocationCard catalog={catalog} />
          </div>
          <div className="order-6 min-w-0 lg:col-start-2 lg:row-start-3">
            <ComponentRecordsCard catalog={catalog} />
          </div>
          <div className="order-7 min-w-0 lg:col-start-2 lg:row-start-4">
            <ComponentHistoryCard
              catalog={catalog}
              snapshots={snapshots}
              childIdentities={childIdentities}
              activeSnapshotId={activeSnapshotId}
            />
          </div>
        </div>
      </div>
    </EvidenceDataProvider>
  )
}
