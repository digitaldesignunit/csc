import { ComponentOverviewDataTable } from '@/components/components/overview/ComponentOverviewDataTable'
import ComponentOverviewPagination from '@/components/components/overview/ComponentOverviewPagination'
import { ComponentModel } from '@/generated/ComponentModel'
import { ComponentOverviewColumns } from '@/components/components/overview/ComponentOverviewColumns'
import { Card } from '@/components/ui/card'
import ComponentOverviewFilterMenu from '@/components/components/overview/ComponentOverviewFilterMenu'
import ComponentUuidNavigator from '@/components/components/overview/ComponentUuidNavigator'
import { Package } from 'lucide-react'

import { headers } from 'next/headers'
import { redirect } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type SearchParams = {
  page?: string
  size?: string
  sortkey?: string
  sortorder?: string
  comptype?: string
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
}

async function fetchComponentsAndTotal({
  page, size, sortkey, sortorder, comptype, material, dataset, validated = 1,
  complexity, fragment, bbx_min_x, bbx_min_y, bbx_min_z, bbx_max_x, bbx_max_y, bbx_max_z,
}: {
  page: number; size: number; sortkey: string; sortorder: 'asc' | 'desc'; comptype: string; material: string; dataset: string; validated?: number
  complexity?: string; fragment?: string; bbx_min_x?: string; bbx_min_y?: string; bbx_min_z?: string
  bbx_max_x?: string; bbx_max_y?: string; bbx_max_z?: string
}) {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''        // <-- forward cookie for middleware & proxy
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const listParams = new URLSearchParams({
    page: String(page),
    size: String(size),
    sortkey,
    sortorder,
    comptype,
    material,
    dataset,
    validated: String(validated),
  })
  
  const countParams = new URLSearchParams({
    comptype,
    material,
    dataset,
    validated: String(validated),
  })

  // Add new filter parameters if they exist
  if (complexity) {
    listParams.set('complexity', complexity)
    countParams.set('complexity', complexity)
  }
  if (fragment) {
    listParams.set('fragment', fragment)
    countParams.set('fragment', fragment)
  }
  if (bbx_min_x) {
    listParams.set('bbx_min_x', bbx_min_x)
    countParams.set('bbx_min_x', bbx_min_x)
  }
  if (bbx_min_y) {
    listParams.set('bbx_min_y', bbx_min_y)
    countParams.set('bbx_min_y', bbx_min_y)
  }
  if (bbx_min_z) {
    listParams.set('bbx_min_z', bbx_min_z)
    countParams.set('bbx_min_z', bbx_min_z)
  }
  if (bbx_max_x) {
    listParams.set('bbx_max_x', bbx_max_x)
    countParams.set('bbx_max_x', bbx_max_x)
  }
  if (bbx_max_y) {
    listParams.set('bbx_max_y', bbx_max_y)
    countParams.set('bbx_max_y', bbx_max_y)
  }
  if (bbx_max_z) {
    listParams.set('bbx_max_z', bbx_max_z)
    countParams.set('bbx_max_z', bbx_max_z)
  }

  const fetchOpts = { cache: 'no-store' as const, headers: { cookie } }

  const [itemsRes, countRes] = await Promise.all([
    fetch(`${base}/api/backend/shallowcomponents?${listParams.toString()}`, fetchOpts),
    fetch(`${base}/api/backend/componentcount?${countParams.toString()}`, fetchOpts),
  ])

  if (itemsRes.status === 401 || countRes.status === 401) {
    redirect('/auth/signin?callbackUrl=/components')
  }
  if (!itemsRes.ok) throw new Error(`Failed to fetch components: ${itemsRes.status} ${await itemsRes.text()}`)
  if (!countRes.ok) throw new Error(`Failed to fetch count: ${countRes.status} ${await countRes.text()}`)

  const items = (await itemsRes.json()) as ComponentModel[]
  const { count: total } = (await countRes.json()) as { count: number }
  return { items, total }
}

export default async function ComponentsPage({
  searchParams,
}: {
  // Next 15: searchParams is async
  searchParams: Promise<SearchParams>
}) {
  const sp = await searchParams

  const page = Number(sp?.page ?? 1)
  const size = Number(sp?.size ?? 20)
  const sortkey = sp?.sortkey ?? '_id'
  const sortorder: 'asc' | 'desc' = sp?.sortorder === 'desc' ? 'desc' : 'asc'
  const comptype = sp?.comptype ?? ''
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

  const { items, total } = await fetchComponentsAndTotal({
    page, size, sortkey, sortorder, comptype, material, dataset, validated: 1,
    complexity, fragment, bbx_min_x, bbx_min_y, bbx_min_z, bbx_max_x, bbx_max_y, bbx_max_z,
  })

  // Debug logging in development
  // if (process.env.NODE_ENV === 'development' && items.length > 0) {
  //   console.log('[ComponentsPage] Sample component data:', items[0])
  //   console.log('[ComponentsPage] Sample bbx structure:', items[0]?.bbx, 'Type:', typeof items[0]?.bbx)
  // }

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Package className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Browse Components</h1>
        </div>
      </div>

      {/* Main Content */}
      <div className="space-y-2">
        {/* Filter Section */}
        <ComponentOverviewFilterMenu
          defaultMaterial={material}
          defaultCompType={comptype}
          defaultDataset={dataset}
          defaultPageSize={size}
        />

        {/* UUID Navigator */}
        <ComponentUuidNavigator />

        {/* Components Table */}
        <Card className="w-full overflow-x-auto p-0">
          <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={items} />
        </Card>

        {/* Pagination */}
        <ComponentOverviewPagination pageNum={page} pageSize={size} total={total} />
      </div>
    </div>
  )
}
