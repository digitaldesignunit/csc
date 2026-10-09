// app/components/[component_id]/page.tsx
import ComponentPageView from '@/components/components/detail/ComponentPageView'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot, type CatalogShallowRow } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { isPublished } from '@/components/components/componentDetailShared'
import Link from 'next/link'
import ComponentAccessNotice from '@/components/components/ComponentAccessNotice'
import ComponentSnapshotVersionList from '@/components/components/ComponentSnapshotVersionList'
import { isTombstone } from '@/lib/backend'
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
    // the author and the moderators of a piece nobody has published yet see
    // its versions (draft, pending, rejected) and their buttons (spec 3.1.5, 7.0)
    const inFlight: SnapshotSummaryItem[] = snapshotsRes.ok ? ((await snapshotsRes.json()) as SnapshotSummaryItem[]) : []
    return (
      <>
        <ComponentAccessNotice
          kind="no-current-state"
          catalogNumber={catalog.identity.catalog_number}
        />
        {inFlight.length > 0 && (
          <div className="container mx-auto max-w-2xl p-4 sm:p-6">
            <ComponentSnapshotVersionList
              identityId={component_id}
              snapshots={inFlight}
              activeSnapshotId=""
              liveSnapshotId=""
              dataset={catalog.identity.dataset}
            />
            <Link
              href={`/components/${encodeURIComponent(component_id)}/edit`}
              className="mt-3 inline-block text-sm font-medium underline underline-offset-4"
            >
              Edit details of the latest version
            </Link>
          </div>
        )}
      </>
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

  return (
    <ComponentPageView
      catalog={catalog}
      snapshots={snapshots}
      childIdentities={childIdentities}
      activeSnapshotId={activeSnapshotId}
      viewingVersion={viewingVersion}
      liveVersion={liveVersion}
      isViewingLive={isViewingLive}
      snapshotStatus={isPublished(snapshot) ? 'published' : snapshot.status}
    />
  )
}
