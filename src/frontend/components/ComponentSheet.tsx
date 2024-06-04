'use client'

import { useState } from "react"
import { Button } from "./ui/button"
import ComponentViewer from "./ComponentViewer"
import ComponentViewerSkeleton from "./ComponentViewerSkeleton"
import { ComponentData } from "./models"
import { 
  Sheet, 
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger } from "./ui/sheet"
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card"
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from "./ui/tooltip"
import { hexComponentColor, componentColorString } from "@/lib/utils"

interface FetchComponentGeometryProps {
  component_id: string
}

const fetch_component_geometry = async ({ component_id }: FetchComponentGeometryProps) => {
  const params = new URLSearchParams(
    { component_id }
  )
  const response = await fetch(
    `${process.env.NEXT_PUBLIC_BASE_URL}/api/fetch-component-geometry?${params.toString()}`,
    {
      method: 'GET',
      cache: 'no-cache'
    }
  )
  if (!response.ok) {
    throw new Error('Failed to fetch component geometry')
  }
  return response.json()
}

function inject_geometry(component: ComponentData, component_geometry: any) {
      component.geometry = component_geometry
}

export default function ComponentSheet({
  component_data,
}: {
  component_data: ComponentData
}) {

  // Component Color
  const component_color_str = componentColorString(component_data.color)
  const component_color_hex = hexComponentColor(component_data.color)

  // Geometry Fetching
  const [fetchedData, setFetchedData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isComponentViewerVisible, setIsComponentViewerVisible] = useState(false);

  const handleButtonClickComponentDetail = async () => {
    setIsLoading(true);
    setIsComponentViewerVisible(false); // Hide ComponentViewer while fetching
    try {
      const component_geometry = await fetch_component_geometry({ component_id: component_data._id });
      inject_geometry(component_data, component_geometry.geometry);
      setFetchedData(component_geometry);
      setIsComponentViewerVisible(true); // Show ComponentViewer once data is fetched
    } catch (error) {
      console.error("Error fetching data:", error);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <Sheet>
      <SheetTrigger asChild>
        <div className='text-left align-text-top cursor-pointer'>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" className="h-5 w-[315px] hover:bg-[#009cda] hover:text-white" onClick={handleButtonClickComponentDetail}>{component_data._id}</Button>
              </TooltipTrigger>
              <TooltipContent>
                Click to preview
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </SheetTrigger>

      <SheetContent side='bottom'>
        <SheetHeader>
          <SheetTitle className="text-center">Component Viewer</SheetTitle>
          <SheetDescription>
            <Card className="m-2">
              <CardHeader>
                <CardTitle className="text-sm text-left">{component_data._id}</CardTitle>
              </CardHeader>
              <CardContent className="text-left">
                Type: {component_data.type} <br/>
                Material: {component_data.material} <br/>
                Material Thickness: {component_data.materialthickness} <br/>
                <div className="flex items-center max-w-12">
                Color: 
                <div className="ml-2 avatar rounded-full min-h-4 min-w-4 max-w-5 max-h-5 items-center justify-left" style={{backgroundColor: component_color_hex}}></div>
                <div className="ml-2 items-center justify-center text-center">{component_color_str}</div>
                </div>
              </CardContent>
            </Card>
          </SheetDescription>
        </SheetHeader>
        {isLoading ? <ComponentViewerSkeleton />: 
        isComponentViewerVisible && <ComponentViewer component_data={component_data} />}
        <SheetFooter>
          <div >
          <SheetClose asChild className="text-center items-center">
            <Button variant="outline">Close</Button>
          </SheetClose>
          </div>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
