import ComponentDetailCard from "@/components/ComponentDetailCard";
import ComponentViewer from "@/components/ComponentViewer";

interface FetchComponentProps {
  component_id: string
}

const fetch_component = async ({ component_id }: FetchComponentProps) => {
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_BASE_URL}/api/fetch-component/${component_id}`,
    {
      method: 'GET',
      cache: 'no-cache'
    }
  )
  if (!response.ok) {
    throw new Error('Failed to fetch component!')
  }
  return response.json()
}

export default async function ComponentDetailPage({
  params,
}: {
  params: { component_id: string };
}) {
  // fetch components from API using search params
  let component_data = await fetch_component(
    {
      component_id: params.component_id
    }
  )
  return (
    <div>
      <ComponentViewer component_data={component_data} />
      <ComponentDetailCard component_data={component_data}/>
  </div>
  )
}
