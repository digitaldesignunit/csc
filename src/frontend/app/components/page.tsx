import { ComponentOverviewDataTable } from '@/components/ComponentOverviewDataTable'
import ComponentOverviewPagination from '@/components/ComponentOverviewPagination'
import { ComponentData } from '@/components/models'
import { ComponentOverviewColumns } from '@/components/ComponentOverviewColumns'
import { Card } from '@/components/ui/card'
import ComponentOverviewFilterMenu from '@/components/ComponentOverviewFilterMenu'

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
}

async function fetchComponentsAndTotal({
  page, size, sortkey, comptype, material, validated = 1,
}: {
  page: number; size: number; sortkey: string; comptype: string; material: string; validated?: number
}) {
  const h = await headers()
  const cookie = h.get('cookie') ?? ''        // <-- forward cookie for middleware & proxy
  const base = `${h.get('x-forwarded-proto') ?? 'http'}://${h.get('host')}`

  const listParams = new URLSearchParams({
    page: String(page),
    size: String(size),
    sortkey,
    comptype,
    material,
    validated: String(validated),
  })
  const countParams = new URLSearchParams({
    comptype,
    material,
    validated: String(validated),
  })

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

  const items = (await itemsRes.json()) as ComponentData[]
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
  const comptype = sp?.comptype ?? ''
  const material = sp?.material ?? ''

  const { items, total } = await fetchComponentsAndTotal({
    page, size, sortkey, comptype, material, validated: 1,
  })

  return (
    <div className="grid gap-2 m-2">
      <ComponentOverviewFilterMenu defaultMaterial={material} defaultCompType={comptype} />
      <Card className="w-full overflow-x-auto p-0">
        <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={items} />
      </Card>
      <ComponentOverviewPagination pageNum={page} pageSize={size} total={total} />
    </div>
  )
}
