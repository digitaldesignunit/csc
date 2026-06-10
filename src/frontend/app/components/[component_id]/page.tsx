// app/components/[component_id]/page.tsx
import ComponentDetailPageLayout from '@/components/components/ComponentDetailPageLayout'
import ComponentDetailSnapshotBanner from '@/components/components/ComponentDetailSnapshotBanner'
import ComponentViewer from '@/components/components/ComponentViewer'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { formatTimestamp } from '@/lib/utils'
import { Archive, Package } from 'lucide-react'
import Link from 'next/link'
import { headers } from 'next/headers'
import { redirect, notFound } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type PageParams = { component_id: string }
type PageSearchParams = { snapshots?: string }

function isConsumedIdentity(consumedAt: unknown): boolean {
  return consumedAt !== undefined && consumedAt !== null && String(consumedAt).trim() !== ''
}

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

  const composeUrl = requestedSnapshotId
    ? `${base}/api/backend/identities/${encodeURIComponent(component_id)}/compose?${new URLSearchParams({ snapshots: requestedSnapshotId }).toString()}`
    : `${base}/api/backend/identities/${encodeURIComponent(component_id)}/compose`

  const [composeRes, snapshotsRes] = await Promise.all([
    fetch(composeUrl, fetchOpts),
    fetch(
      `${base}/api/backend/identities/${encodeURIComponent(component_id)}/snapshots`,
      fetchOpts,
    ),
  ])

  const res = composeRes

  if (res.status === 401) {
    const callback = requestedSnapshotId
      ? `/components/${component_id}?snapshots=${encodeURIComponent(requestedSnapshotId)}`
      : `/components/${component_id}`
    redirect(`/auth/signin?callbackUrl=${encodeURIComponent(callback)}`)
  }
  if (res.status === 404) {
    notFound()
  }
  if (!res.ok) {
    const body = await res.text()
    throw new Error(
      `Failed to fetch compose ${component_id}: ${res.status} ${body}`,
    )
  }

  const catalog = (await res.json()) as CatalogComponent
  const snapshot = primarySnapshot(catalog)
  let snapshots: SnapshotSummaryItem[] = []
  if (snapshotsRes.ok) {
    snapshots = (await snapshotsRes.json()) as SnapshotSummaryItem[]
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

  const isConsumed = isConsumedIdentity(catalog.identity.consumed_at)
  const consumedAtLabel =
    isConsumed && catalog.identity.consumed_at
      ? formatTimestamp(String(catalog.identity.consumed_at))
      : null

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      <div className="mb-4 sm:mb-6 space-y-4">
        <div className="flex items-center gap-2 sm:gap-3">
          {isConsumed ? (
            <Archive className="h-6 w-6 text-primary" />
          ) : (
            <Package className="h-6 w-6 text-primary" />
          )}
          <h1 className="text-xl sm:text-2xl font-bold">
            {isConsumed ? 'Consumed Component' : 'Component Details'}
          </h1>
        </div>

        {isConsumed && (
          <div
            role="status"
            className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100"
          >
            <p className="font-medium">This identity is consumed</p>
            <p className="mt-1 text-sm text-amber-900/90 dark:text-amber-100/90">
              It no longer appears in the active catalog
              {consumedAtLabel ? ` (marked ${consumedAtLabel})` : ''}.
              Admins can restore it from the actions below.
            </p>
            <Link
              href="/components?consumed=1"
              className="mt-2 inline-block text-sm font-medium underline underline-offset-4 hover:no-underline"
            >
              Browse consumed components
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
            isPending={!snapshot.validated}
          />
        )}
        <ComponentViewer catalog={catalog} />
        <ComponentDetailPageLayout
          catalog={catalog}
          snapshots={snapshots}
          activeSnapshotId={activeSnapshotId}
          liveSnapshotId={liveSnapshotId}
        />
      </div>
    </div>
  )
}
