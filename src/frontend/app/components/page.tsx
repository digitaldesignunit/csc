import { ComponentOverviewDataTable } from '@/components/ComponentOverviewDataTable'
import ComponentOverviewPagination from '@/components/ComponentOverviewPagination'
import { ComponentData } from '@/components/models'
import { ComponentOverviewColumns } from '@/components/ComponentOverviewColumns'
import { Card } from '@/components/ui/card'
import ComponentOverviewFilterMenu from '@/components/ComponentOverviewFilterMenu'

interface FetchComponentsProps {
  page: number
  size: number
  sortkey: string
  comptype: string
  material: string
}

const fetch_components_shallow = async ({ page, size, sortkey, comptype, material }: FetchComponentsProps) => {
  const params = new URLSearchParams(
    { page: page.toString(),
      size: size.toString(),
      sortkey: sortkey.toString(),
      comptype: comptype.toString(),
      material: material.toString()
      
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
    material?: string
  }
}) {
  // search params retrieval
  let page = Number(searchParams?.page) || 1
  let size = Number(searchParams?.size) || 20
  let sortkey = searchParams?.sortkey || '_id'
  let comptype = searchParams?.comptype || ''
  let material = searchParams?.material || ''

  // fetch components from API using search params
  let db_components = await fetch_components_shallow(
    {
      page: page,
      size: size,
      sortkey: sortkey,
      comptype: comptype,
      material: material
    }
  )

  return (
    <>
      <div className="grid gap-2 m-2">
      {/* 1) Render the FilterMenu, passing in default values from search params */}
      <ComponentOverviewFilterMenu
        defaultMaterial={material}
        defaultCompType={comptype}
      />

      {/* 2) The data table */}
      <Card className="max-w-fit overflow-x-auto">
        <ComponentOverviewDataTable
          columns={ComponentOverviewColumns}
          data={db_components as ComponentData[]}
        />
      </Card>

      {/* 3) Pagination, if needed */}
      <ComponentOverviewPagination pageNum={page} pageSize={size} />
    </div>
    </>
  )
}
