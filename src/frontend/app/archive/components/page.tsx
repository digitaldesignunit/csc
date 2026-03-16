import ComponentOverviewPagination from '@/components/components/overview/ComponentOverviewPagination'
import ComponentOverviewDataTableWithConfig from '@/components/components/overview/ComponentOverviewDataTableWithConfig'
import { ComponentModel } from '@/generated/ComponentModel'
import { Card } from '@/components/ui/card'
import ComponentOverviewFilterMenu from '@/components/components/overview/ComponentOverviewFilterMenu'
import { Archive } from 'lucide-react'
import { headers } from 'next/headers'
import { redirect } from 'next/navigation'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

type SearchParams = {
  page?: string
  size?: string
  sortkey?: string
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

async function fetchArchivedComponentsAndTotal({
  page, size, sortkey, comptype, material, dataset,
  complexity, fragment, bbx_min_x, bbx_min_y, bbx_min_z, bbx_max_x, bbx_max_y, bbx_max_z,
}: {
  page: number; size: number; sortkey: string; comptype: string; material: string; dataset: string
  complexity?: string; fragment?: string; bbx_min_x?: string; bbx_min_y?: string; bbx_min_z?: string
  bbx_max_x?: string; bbx_max_y?: string; bbx_max_z?: string
}) {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const listParams = new URLSearchParams({
    page: String(page),
    size: String(size),
    sortkey,
    comptype,
    material,
    dataset,
  })

  const countParams = new URLSearchParams({
    comptype,
    material,
    dataset,
  })

  // Add filter parameters if they exist
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
    fetch(`${base}/api/backend/archived/shallowcomponents?${listParams.toString()}`, fetchOpts),
    fetch(`${base}/api/backend/archived/componentcount?${countParams.toString()}`, fetchOpts),
  ])

  if (itemsRes.status === 401 || countRes.status === 401) {
    redirect('/auth/signin?callbackUrl=/archive/components')
  }
  if (itemsRes.status === 403 || countRes.status === 403) {
    redirect('/')
  }
  if (!itemsRes.ok) throw new Error(`Failed to fetch archived components: ${itemsRes.status} ${await itemsRes.text()}`)
  if (!countRes.ok) throw new Error(`Failed to fetch count: ${countRes.status} ${await countRes.text()}`)

  const items = (await itemsRes.json()) as ComponentModel[]
  const { count: total } = (await countRes.json()) as { count: number }
  return { items, total }
}

// Archive-specific preview cell config
const archivePreviewConfig = { isArchived: true }

export default async function ArchivePage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>
}) {
  const sp = await searchParams

  const page = Number(sp?.page ?? 1)
  const size = Number(sp?.size ?? 20)
  const sortkey = sp?.sortkey ?? '_id'
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

  const { items, total } = await fetchArchivedComponentsAndTotal({
    page, size, sortkey, comptype, material, dataset,
    complexity, fragment, bbx_min_x, bbx_min_y, bbx_min_z, bbx_max_x, bbx_max_y, bbx_max_z,
  })

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-full">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Archive className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Component Archive</h1>
        </div>
        <p className="text-muted-foreground">
          Browse and restore archived components. These components are not visible in the main Catalog.
        </p>
      </div>

      {/* Main Content */}
      <div className="space-y-2">
        {/* Filter Section */}
        <ComponentOverviewFilterMenu
          defaultMaterial={material}
          defaultCompType={comptype}
          defaultDataset={dataset}
          datasetsEndpoint="/api/backend/archived/datasets"
        />

        {/* Components Table */}
        <Card className="w-full overflow-x-auto p-0">
          <ComponentOverviewDataTableWithConfig data={items} previewConfig={archivePreviewConfig} />
        </Card>

        {/* Pagination */}
        <ComponentOverviewPagination pageNum={page} pageSize={size} total={total} />
      </div>
    </div>
  )
}

