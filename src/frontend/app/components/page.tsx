import { ComponentOverviewDataTable } from '@/components/components/overview/ComponentOverviewDataTable'
import ComponentOverviewPagination from '@/components/components/overview/ComponentOverviewPagination'
import { ComponentOverviewColumns } from '@/components/components/overview/ComponentOverviewColumns'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import ComponentOverviewFilterMenu from '@/components/components/overview/ComponentOverviewFilterMenu'
import ComponentUuidNavigator from '@/components/components/overview/ComponentUuidNavigator'
import type { CatalogShallowRow } from '@/generated/catalogExtras'
import Link from 'next/link'
import { cn } from '@/lib/utils'
import { Archive, Package } from 'lucide-react'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type SearchParams = {
  page?: string
  size?: string
  sortkey?: string
  sortorder?: string
  original_function?: string
  material?: string
  dataset?: string
  complexity?: string
  fragment?: string
  bbx_min_x?: string
  bbx_min_y?: string
  bbx_min_z?: string
  bbx_max_x?: string
  bbx_max_y?: string
  bbx_max_z?: string
  circulation?: string
}

export default async function ComponentsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const sp = await searchParams
  const showConsumed = sp?.circulation === 'exited'

  const page = Number(sp?.page ?? 1)
  const size = Number(sp?.size ?? 20)
  const sortkey = sp?.sortkey ?? '_id'
  const sortorder: 'asc' | 'desc' = sp?.sortorder === 'desc' ? 'desc' : 'asc'
  const originalFunction = sp?.original_function ?? ''
  const material = sp?.material ?? ''
  const dataset = sp?.dataset ?? ''
  const complexity = sp?.complexity ?? ''
  const fragment = sp?.fragment ?? ''
  const bbx_min_x = sp?.bbx_min_x ?? ''
  const bbx_min_y = sp?.bbx_min_y ?? ''
  const bbx_min_z = sp?.bbx_min_z ?? ''
  const bbx_max_x = sp?.bbx_max_x ?? ''
  const bbx_max_y = sp?.bbx_max_y ?? ''
  const bbx_max_z = sp?.bbx_max_z ?? ''

  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const circulation = showConsumed ? 'exited' : 'active'
  const signInCallback = showConsumed ? '/components?circulation=exited' : '/components'

  const listParams = new URLSearchParams({
    page: String(page),
    size: String(size),
    sortkey,
    sortorder,
    original_function: originalFunction,
    material,
    dataset,
    circulation,
    expand: 'shallow',
  })

  const countParams = new URLSearchParams({
    original_function: originalFunction,
    material,
    dataset,
    circulation,
  })

  for (const [key, value] of [
    ['complexity', complexity],
    ['fragment', fragment],
    ['bbx_min_x', bbx_min_x],
    ['bbx_min_y', bbx_min_y],
    ['bbx_min_z', bbx_min_z],
    ['bbx_max_x', bbx_max_x],
    ['bbx_max_y', bbx_max_y],
    ['bbx_max_z', bbx_max_z],
  ] as const) {
    if (value) {
      listParams.set(key, value)
      countParams.set(key, value)
    }
  }

  const fetchOpts = { cache: 'no-store' as const, headers: { cookie } }

  const [itemsRes, countRes] = await Promise.all([
    fetch(`${base}/api/backend/identities?${listParams.toString()}`, fetchOpts),
    fetch(`${base}/api/backend/identities/count?${countParams.toString()}`, fetchOpts),
  ])

  if (itemsRes.status === 401 || countRes.status === 401) {
    redirect(`/auth/signin?callbackUrl=${encodeURIComponent(signInCallback)}`)
  }
  if (!itemsRes.ok) {
    throw new Error(
      `Failed to fetch identities: ${itemsRes.status} ${await itemsRes.text()}`,
    )
  }
  if (!countRes.ok) {
    throw new Error(
      `Failed to fetch identity count: ${countRes.status} ${await countRes.text()}`,
    )
  }

  const items = (await itemsRes.json()) as CatalogShallowRow[]
  const { count: total } = (await countRes.json()) as { count: number }

  const datasetsEndpoint = `/api/backend/identities/meta/datasets?circulation=${circulation}`

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      <div className="mb-4 sm:mb-6 space-y-3">
        <div className="flex items-center gap-2 sm:gap-3">
          {showConsumed ? (
            <Archive className="h-6 w-6 text-primary" />
          ) : (
            <Package className="h-6 w-6 text-primary" />
          )}
          <h1 className="text-xl sm:text-2xl font-bold">
            {showConsumed ? 'Components out of circulation' : 'Browse Components'}
          </h1>
        </div>
        {showConsumed && (
          <p className="text-muted-foreground">
            Pieces that left circulation: split, installed elsewhere, recycled,
            returned or lost. Open any row for the same detail view.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            asChild
            size="sm"
            variant={showConsumed ? 'outline' : 'default'}
            className={cn(
              !showConsumed &&
                'border-green-600 bg-green-600 text-white hover:bg-green-700 hover:text-white dark:border-green-600 dark:bg-green-600 dark:hover:bg-green-700',
            )}
          >
            <Link href="/components">Active Catalog</Link>
          </Button>
          <Button
            asChild
            size="sm"
            variant={showConsumed ? 'default' : 'outline'}
            className={cn(
              showConsumed &&
                'border-orange-600 bg-orange-600 text-white hover:bg-orange-700 hover:text-white dark:border-orange-600 dark:bg-orange-600 dark:hover:bg-orange-700',
            )}
          >
            <Link href="/components?circulation=exited">Out of circulation</Link>
          </Button>
        </div>
      </div>

      <div className="space-y-2">
        <ComponentOverviewFilterMenu
          defaultMaterial={material}
          defaultOriginalFunction={originalFunction}
          defaultDataset={dataset}
          defaultPageSize={size}
          datasetsEndpoint={datasetsEndpoint}
        />

        {!showConsumed && <ComponentUuidNavigator />}

        <Card className="w-full overflow-x-auto p-0">
          <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={items} />
        </Card>

        <ComponentOverviewPagination pageNum={page} pageSize={size} total={total} />
      </div>
    </div>
  )
}
