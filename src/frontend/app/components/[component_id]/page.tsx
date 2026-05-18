// app/components/[component_id]/page.tsx
import ComponentDetailCard from '@/components/components/ComponentDetailCard'
import ComponentSnapshotPhotoGallery from '@/components/components/ComponentSnapshotPhotoGallery'
import ComponentViewer from '@/components/components/ComponentViewer'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { formatTimestamp } from '@/lib/utils'
import { Archive, Package } from 'lucide-react'
import Link from 'next/link'
import { headers } from 'next/headers'
import { redirect, notFound } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type PageParams = { component_id: string }

function isConsumedIdentity(consumedAt: unknown): boolean {
  return consumedAt !== undefined && consumedAt !== null && String(consumedAt).trim() !== ''
}

export default async function ComponentDetailPage({
  params,
}: {
  params: Promise<PageParams>
}) {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const { component_id } = await params

  const res = await fetch(
    `${base}/api/backend/identities/${encodeURIComponent(component_id)}/compose`,
    {
      cache: 'no-store',
      headers: { cookie },
    },
  )

  if (res.status === 401) {
    redirect(`/auth/signin?callbackUrl=/components/${component_id}`)
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
  const isConsumed = isConsumedIdentity(catalog.identity.consumed_at)
  const consumedAtLabel =
    isConsumed && catalog.identity.consumed_at
      ? formatTimestamp(String(catalog.identity.consumed_at))
      : null

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      <div className="mb-6 sm:mb-8 space-y-4">
        <div className="flex items-center gap-2 sm:gap-3">
          {isConsumed ? (
            <Archive className="h-8 w-8 text-primary" />
          ) : (
            <Package className="h-8 w-8 text-primary" />
          )}
          <h1 className="text-2xl sm:text-3xl font-bold">
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
        <ComponentViewer catalog={catalog} />
        <ComponentSnapshotPhotoGallery
          snapshotId={String(catalog.snapshot._id ?? catalog.identity.current_snapshot_id)}
          photoCountHint={
            typeof catalog.snapshot.photo_count === 'number'
              ? catalog.snapshot.photo_count
              : 0
          }
        />
        <ComponentDetailCard catalog={catalog} />
      </div>
    </div>
  )
}
