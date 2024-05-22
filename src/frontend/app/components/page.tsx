import { ComponentOverviewDataTable } from "@/components/ComponentOverviewDataTable";
import ComponentOverviewPagination from "@/components/ComponentOverviewPagination";
import { ComponentData } from "@/components/models";
import { ComponentOverviewColumns } from "@/components/ComponentOverviewColumns";
import { Card } from "@/components/ui/card";

// const fetch_componentcount = async (retried: boolean = false) => {
//   const endpoint_url = 'https://api.ddu.uber.space/componentcount'
//   let headers = await create_headers(API_TOKEN)
//   let count: Number = await fetch(
//     endpoint_url,
//     {
//       method: 'GET',
//       mode: 'cors',
//       headers: headers,
//       cache: 'no-store'
//     }
//   ).then( async (response) => {
//     console.log(`Component Count Response Status: ${response.status}`)
//     if (response.status == 401 && !retried) {
//       console.log('Response Unauthorized! Attempting Retry...')
//       return await fetch_componentcount(true)
//     }
//     return response.json()
//   }).catch(async (err) => {
//     if (!retried) {
//       console.log('Component Count Response Rejected!')
//       console.log(`Error: ${err}`)
//       console.log('Attempting retry...')
//       return await fetch_componentcount(true)
//     } else {
//       console.log('Component Count 2nd Response Rejected! Aborting...')
//       console.log(`Error: ${err}`)
//       return []
//     }
//   });
//   return count
// }

interface FetchComponentsProps {
  page: number;
  size: number;
  comptype: string;
  sortkey: string;
}

const fetch_components = async ({ page, size, comptype, sortkey }: FetchComponentsProps) => {
  const params = new URLSearchParams(
    { page: page.toString(),
      size: size.toString(),
      comptype,
      sortkey
    }
  )
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_BASE_URL}/api/fetch-components?${params.toString()}`,
    {
    method: 'GET',
    cache: 'no-store'}
  )
  if (!response.ok) {
    throw new Error('Failed to fetch components');
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
    detail?: string
  };
}) {
  // search params retrieval
  let page = Number(searchParams?.page) || 1
  let size = Number(searchParams?.size) || 10
  let sortkey = searchParams?.sortkey || '_id'
  let comptype = searchParams?.comptype || ''

  // fetch components from API using search params
  let db_components = await fetch_components(
    {
      page: page,
      size: size,
      comptype: comptype,
      sortkey: sortkey
    }
  )

  return (
    <>
      <div className="grid gap-[32px] m-4">
        <Card>
          <ComponentOverviewDataTable columns={ComponentOverviewColumns} data={db_components as ComponentData[]} />
        </Card>
        <ComponentOverviewPagination pageNum={page} pageSize={size}/>
      </div>

    </>
  );
}
