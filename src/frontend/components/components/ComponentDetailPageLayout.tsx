'use client'

import type { ReactNode } from 'react'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { ComponentLocation } from '@/generated/CatalogSharedTypes'
import { useSession } from 'next-auth/react'
import Link from 'next/link'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import ComponentDetailActions from './ComponentDetailActions'
import ComponentDetailLocationPanel from './ComponentDetailLocationPanel'
import ComponentDetailMetadataTabs from './ComponentDetailMetadataTabs'
import ComponentDetailSummary from './ComponentDetailSummary'
import ComponentSnapshotPhotoGallery from './ComponentSnapshotPhotoGallery'
import ComponentSnapshotVersionList from './ComponentSnapshotVersionList'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import type { CatalogShallowRow } from '@/generated/catalogExtras'

type ComponentDetailPageLayoutProps = {
  catalog: CatalogComponent
  snapshots?: SnapshotSummaryItem[]
  activeSnapshotId: string
  liveSnapshotId: string
  childIdentities?: CatalogShallowRow[]
  children: ReactNode
}

export default function ComponentDetailPageLayout({
  catalog,
  snapshots = [],
  activeSnapshotId,
  liveSnapshotId,
  childIdentities = [],
  children,
}: ComponentDetailPageLayoutProps) {
  const { data: session } = useSession()
  const { identity } = catalog
  const snapshot = primarySnapshot(catalog)
  const identityId = String(identity._id ?? '')
  const snapshotId = String(snapshot._id ?? identity.current_snapshot_id)
  const location = (snapshot.location as ComponentLocation) ?? { lat: 0, lon: 0 }
  const isPublicIdentity =
    (identity as unknown as { is_public?: boolean }).is_public === true
  const isPublicDemoView = isPublicIdentity && !session?.user

  return (
    <div
      className={cn(
        'grid items-start content-start gap-6 2xl:gap-x-6 2xl:gap-y-4',
        isPublicDemoView
          ? '[grid-template-areas:"banner"_"viewer"_"identity"_"media"] lg:[grid-template-areas:"banner_banner"_"viewer_viewer"_"identity_media"] 2xl:[grid-template-areas:"banner_banner"_"identity_stage"]'
          : '[grid-template-areas:"viewer"_"identity"_"media"] lg:[grid-template-areas:"viewer_viewer"_"identity_media"] 2xl:[grid-template-areas:"identity_stage"]',
        'lg:grid-cols-[minmax(20rem,24rem)_minmax(0,1fr)]',
      )}
    >
      {isPublicDemoView && (
        <div
          role="status"
          className="[grid-area:banner] rounded-lg border border-sky-300 bg-sky-50 px-4 py-3 text-sky-950 dark:border-sky-700 dark:bg-sky-950/40 dark:text-sky-100"
        >
          <p className="font-medium">Public demo view</p>
          <p className="mt-1 text-sm text-sky-900/90 dark:text-sky-100/90">
            This component is shared without login.{' '}
            <Link href="/auth/signin" className="font-medium underline underline-offset-4 hover:no-underline">
              Sign in
            </Link>{' '}
            for catalog actions and reservation workflows.
          </p>
        </div>
      )}

      <div className="contents 2xl:flex 2xl:min-w-0 2xl:flex-col 2xl:gap-4 2xl:[grid-area:stage]">
        <div className="min-w-0 [grid-area:viewer]">{children}</div>

        <div className="min-w-0 space-y-4 [grid-area:media] 2xl:grid 2xl:grid-cols-2 2xl:gap-4 2xl:space-y-0">
          <ComponentSnapshotPhotoGallery
            snapshotId={snapshotId}
            photoCount={snapshot.photo_count}
            compact
          />
          <ComponentDetailLocationPanel location={location} />
        </div>
      </div>

      <Card className="min-w-0 w-full shadow-sm [grid-area:identity]">
        <CardContent className="space-y-3 pt-5">
          <ComponentDetailSummary catalog={catalog} />
          <ComponentDetailActions catalog={catalog} />
          <ComponentSnapshotVersionList
            identityId={identityId}
            snapshots={snapshots}
            activeSnapshotId={activeSnapshotId}
            liveSnapshotId={liveSnapshotId}
          />
          <ComponentDetailMetadataTabs
            catalog={catalog}
            mode="all"
            childIdentities={childIdentities}
          />
        </CardContent>
      </Card>
    </div>
  )
}
