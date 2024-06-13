import { ComponentOverviewDataTable } from '@/components/ComponentOverviewDataTable'
import ComponentOverviewPagination from '@/components/ComponentOverviewPagination'
import { ComponentData } from '@/components/models'
import { ComponentOverviewColumns } from '@/components/ComponentOverviewColumns'
import { Card } from '@/components/ui/card'

interface FetchComponentsProps {
  page: number
  size: number
  comptype: string
  sortkey: string
}

const fetch_components_shallow = async ({ page, size, comptype, sortkey }: FetchComponentsProps) => {
  const params = new URLSearchParams(
    { page: page.toString(),
      size: size.toString(),
      comptype: comptype.toString(),
      sortkey: sortkey.toString()
    }
  )
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_BASE_URL}/api/fetch-components-shallow?${params.toString()}`,
    {
      method: 'GET',
      cache: 'no-cache'
    }
  )
  if (!response.ok) {
    throw new Error('Failed to fetch components')
  }
  return response.json()
}

export default async function ComponentsPage({
  searchParams,
}: {
  searchParams?: {
    page?: string
    size?: string
    sortkey?: string
    comptype?: string
    detail_id?: string
  }
}) {
  // search params retrieval
  let page = Number(searchParams?.page) || 1
  let size = Number(searchParams?.size) || 20
  let sortkey = searchParams?.sortkey || '_id'
  let comptype = searchParams?.comptype || ''
  let detail_id = searchParams?.detail_id || ''

  // fetch components from API using search params
  let db_components = await fetch_components_shallow(
    {
      page: page,
      size: size,
      comptype: comptype,
      sortkey: sortkey
    }
  )

  return (
    <>
      <div className='grid gap-[32px] m-4'>
        <Card className='max-w-fit overflow-x-auto'>
          <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={db_components as ComponentData[]} />
        </Card>
        <ComponentOverviewPagination pageNum={page} pageSize={size}/>
      </div>
    </>
  )
}
