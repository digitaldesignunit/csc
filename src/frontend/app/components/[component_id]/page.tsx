// app/components/[component_id]/page.tsx
import ComponentDetailPageLayout from '@/components/components/ComponentDetailPageLayout'
import ComponentDetailSnapshotBanner from '@/components/components/ComponentDetailSnapshotBanner'
import ComponentViewer from '@/components/components/ComponentViewer'
import ComponentEvidenceSection from '@/components/evidence/ComponentEvidenceSection'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot, type CatalogShallowRow } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { exitSummary, geometryFailed, isOutOfCirculation, isPublished } from '@/components/components/componentDetailShared'
import { Archive, Package } from 'lucide-react'
import Link from 'next/link'
import RecordRecentComponent from '@/components/layout/RecordRecentComponent'
import ComponentAccessNotice from '@/components/components/ComponentAccessNotice'
import { isTombstone } from '@/lib/backend'
import { formatTimestamp } from '@/lib/utils'
import { headers } from 'next/headers'
import { redirect, notFound } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type PageParams = { component_id: string }
type PageSearchParams = { snapshots?: string }

export default async function ComponentDetailPage({
  params,
  searchParams,
}: {
  params: Promise<PageParams>
  searchParams: Promise<PageSearchParams>
}) {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const { component_id } = await params
  const { snapshots: requestedSnapshotId } = await searchParams

  const fetchOpts = { cache: 'no-store' as const, headers: { cookie } }

  const passportUrl = requestedSnapshotId
    ? `${base}/api/backend/identities/${encodeURIComponent(component_id)}/compose?${new URLSearchParams({ snapshots: requestedSnapshotId }).toString()}`
    : `${base}/api/backend/identities/${encodeURIComponent(component_id)}/compose`

  const [passportRes, snapshotsRes, childrenRes] = await Promise.all([
    fetch(passportUrl, fetchOpts),
    fetch(
      `${base}/api/backend/identities/${encodeURIComponent(component_id)}/snapshots`,
      fetchOpts,
    ),
    fetch(
      `${base}/api/backend/identities/${encodeURIComponent(component_id)}/children`,
      fetchOpts,
    ),
  ])

  const res = passportRes

  // a piece the viewer cannot see is explained, not hidden (8.11, 8.17)
  if (res.status === 401) {
    const callback = requestedSnapshotId
      ? `/components/${component_id}?snapshots=${encodeURIComponent(requestedSnapshotId)}`
      : `/components/${component_id}`
    return <ComponentAccessNotice kind="not-public" callbackUrl={callback} />
  }
  if (res.status === 403) {
    return <ComponentAccessNotice kind="no-access" />
  }
  if (res.status === 410) {
    return <ComponentAccessNotice kind="purged" />
  }
  if (res.status === 404) {
    notFound()
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to fetch passport ${component_id}: ${res.status} ${body}`,
    )
  }

  const body = (await res.json()) as unknown
  if (isTombstone(body)) {
    if (body.duplicate_of) {
      redirect(`/components/${encodeURIComponent(body.duplicate_of)}`)
    }
    return (
      <ComponentAccessNotice
        kind="withdrawn"
        withdrawnAt={body.withdrawn_at}
        catalogNumber={body.catalog_number}
      />
    )
  }
  const catalog = body as CatalogComponent
  if (!catalog.snapshots?.length) {
    return (
      <ComponentAccessNotice
        kind="no-current-state"
        catalogNumber={catalog.identity.catalog_number}
      />
    )
  }
  const snapshot = primarySnapshot(catalog)
  let snapshots: SnapshotSummaryItem[] = []
  if (snapshotsRes.ok) {
    snapshots = (await snapshotsRes.json()) as SnapshotSummaryItem[]
  }
  let childIdentities: CatalogShallowRow[] = []
  if (childrenRes.ok) {
    const body = (await childrenRes.json()) as CatalogShallowRow[]
    if (Array.isArray(body)) {
      childIdentities = body
    }
  }

  const liveSnapshotId = String(catalog.identity.current_snapshot_id ?? '')
  const activeSnapshotId = String(snapshot._id ?? liveSnapshotId)
  const isViewingLive = activeSnapshotId === liveSnapshotId
  const liveVersion =
    snapshots.find((row) => row._id === liveSnapshotId)?.version ??
    (typeof snapshot.version === 'number' && isViewingLive
      ? snapshot.version
      : snapshots.find((row) => row.is_current)?.version ?? 0)
  const viewingVersion =
    typeof snapshot.version === 'number'
      ? snapshot.version
      : snapshots.find((row) => row._id === activeSnapshotId)?.version ?? 0

  const isConsumed = isOutOfCirculation(catalog.identity)
  const exitLabel = exitSummary(catalog.identity.exit)

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      <RecordRecentComponent
        id={String(catalog.identity._id)}
        label={`#${catalog.identity.catalog_number} ${snapshot.name ?? ''}`.trim()}
      />
      <div className="mb-4 sm:mb-6 space-y-4">
        <div className="flex items-center gap-2 sm:gap-3">
          {isConsumed ? (
            <Archive className="h-6 w-6 text-primary" />
          ) : (
            <Package className="h-6 w-6 text-primary" />
          )}
          <h1 className="text-xl sm:text-2xl font-bold">
            {isConsumed ? 'Component out of circulation' : 'Component Details'}
          </h1>
        </div>

        {geometryFailed(snapshot) && (
          <div
            role="status"
            className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-950 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100"
          >
            <p className="font-medium">The geometry of this version could not be processed.</p>
            <p className="mt-1 text-sm opacity-90">
              Orientation, size, shape class and proxies shown here still describe the
              previous geometry. The maintainers can see the cause.
            </p>
          </div>
        )}

        {catalog.identity.withdrawn && (
          <div
            role="status"
            className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-red-950 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100"
          >
            <p className="font-medium">
              Withdrawn on {formatTimestamp(catalog.identity.withdrawn.at)}: {catalog.identity.withdrawn.reason}
            </p>
            <p className="mt-1 text-sm opacity-90">
              Only members of its dataset see this record; everyone else sees that it was withdrawn.
            </p>
          </div>
        )}

        {isConsumed && (
          <div
            role="status"
            className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
          >
            <p className="font-medium">This piece left circulation: {exitLabel}</p>
            <p className="mt-1 text-sm text-amber-900/90 dark:text-amber-100/90">
              It no longer appears in the active catalog; its record stays.
            </p>
            <Link
              href="/components?circulation=exited"
              className="mt-2 inline-block text-sm font-medium underline underline-offset-4 hover:no-underline"
            >
              Browse components out of circulation
            </Link>
          </div>
        )}
      </div>

      <div className="space-y-6">
        {!isViewingLive && (
          <ComponentDetailSnapshotBanner
            identityId={component_id}
            viewingVersion={viewingVersion}
            liveVersion={liveVersion}
            isPending={!isPublished(snapshot)}
          />
        )}
        <ComponentDetailPageLayout
          catalog={catalog}
          snapshots={snapshots}
          activeSnapshotId={activeSnapshotId}
          liveSnapshotId={liveSnapshotId}
          childIdentities={childIdentities}
        >
          <ComponentViewer catalog={catalog} compactDesktop />
        </ComponentDetailPageLayout>
        <ComponentEvidenceSection catalog={catalog} />
      </div>
    </div>
  )
}
