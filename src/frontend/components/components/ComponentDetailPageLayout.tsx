'use client'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { ComponentLocation } from '@/generated/ComponentModel'
import { Card, CardContent } from '@/components/ui/card'
import ComponentDetailActions from './ComponentDetailActions'
import ComponentDetailLocationPanel from './ComponentDetailLocationPanel'
import ComponentDetailMetadataTabs, {
  ComponentDetailCatalogMetadata,
} from './ComponentDetailMetadataTabs'
import ComponentDetailSummary from './ComponentDetailSummary'
import ComponentSnapshotPhotoGallery from './ComponentSnapshotPhotoGallery'

type ComponentDetailPageLayoutProps = {
  catalog: CatalogComponent
}

export default function ComponentDetailPageLayout({ catalog }: ComponentDetailPageLayoutProps) {
  const { identity, snapshot } = catalog
  const snapshotId = String(snapshot._id ?? identity.current_snapshot_id)
  const photoCountHint =
    typeof snapshot.photo_count === 'number' ? snapshot.photo_count : 0
  const location = (snapshot.location as ComponentLocation) ?? { lat: 0, lon: 0 }

  return (
    <div
      className="grid items-start gap-6 lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)] 2xl:grid-cols-[minmax(0,28rem)_minmax(0,30rem)_minmax(0,1fr)]"
    >
      <Card className="min-w-0 w-full shadow-sm lg:max-w-md 2xl:max-w-none">
        <CardContent className="space-y-4 pt-6">
          <ComponentDetailSummary catalog={catalog} />
          <ComponentDetailActions catalog={catalog} />

          <section className="hidden border-t border-border pt-4 2xl:block">
            <h3 className="mb-3 border-b border-border pb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              Catalog
            </h3>
            <ComponentDetailCatalogMetadata catalog={catalog} />
          </section>

          <div className="2xl:hidden">
            <ComponentDetailMetadataTabs catalog={catalog} mode="all" />
          </div>
        </CardContent>
      </Card>

      <Card className="hidden min-w-0 shadow-sm 2xl:block">
        <CardContent className="pt-6">
          <ComponentDetailMetadataTabs catalog={catalog} mode="secondary" />
        </CardContent>
      </Card>

      <div className="min-w-0 space-y-4 lg:sticky lg:top-6">
        <ComponentSnapshotPhotoGallery
          snapshotId={snapshotId}
          photoCountHint={photoCountHint}
          compact
        />
        <ComponentDetailLocationPanel location={location} />
      </div>
    </div>
  )
}
