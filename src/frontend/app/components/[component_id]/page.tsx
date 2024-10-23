import ComponentDetailCard from "@/components/ComponentDetailCard";
import ComponentViewer from "@/components/ComponentViewer";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { componentColorString, hexComponentColor } from "@/lib/utils";
import Link from "next/link";

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

  // Component Color
  const component_color_str = componentColorString(component_data.color)
  const component_color_hex = hexComponentColor(component_data.color)

  return (
    <div>
      {/* <ComponentDetailCard params={{component_id: params.component_id}}/> */}
    
    <Card className='m-2'>
    <CardHeader>

      <CardTitle className='text-sm text-left'>{component_data._id}</CardTitle>

      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Link href={`/findcomponent?reference_id=${component_data._id}`}>
              <Button variant='outline' className='h-8 hover:bg-[#009cda] hover:text-white mt-4'>
                Find Component
              </Button>
            </Link>
          </TooltipTrigger>
          <TooltipContent>
            <div className='flex flex-col text-center'>
              Find this component using the QR code
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    </CardHeader>

    <CardContent className='text-left'>
      Type: {component_data.type} <br/>
      Material: {component_data.material} <br/>
      Material Thickness: {component_data.materialthickness} <br/>
      <div className='flex items-center max-w-12'>
        Color: 
        <div className='ml-2 avatar rounded-full min-h-4 min-w-4 max-w-5 max-h-5 items-center justify-left' style={{backgroundColor: component_color_hex}}></div>
        <div className='ml-2 items-center justify-center text-center'>{component_color_str}</div>
      </div>
    </CardContent>

    </Card>

    <ComponentViewer component_data={component_data} />
  </div>
  )
}
