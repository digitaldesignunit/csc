'use client'

import { useState } from 'react'
import { Button } from './ui/button'
import ComponentViewer from './ComponentViewer'
import ComponentViewerSkeleton from './ComponentViewerSkeleton'
import { ComponentData } from './models'
import { 
  Sheet, 
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger } from './ui/sheet'
import { Tooltip, TooltipProvider, TooltipTrigger, TooltipContent } from './ui/tooltip'
import ComponentPreviewImage from './ComponentPreviewImage'
import Link from 'next/link'

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

export default function ComponentOverviewDataTablePreviewCell({
  component_data,
}: {
  component_data: ComponentData,
}) {
  // Geometry Fetching
  const [isLoading, setIsLoading] = useState(false)
  const [isComponentViewerVisible, setIsComponentViewerVisible] = useState(false)

  // Handle Button Click to fetch and inject Component Geometry
  const handleButtonClickComponentDetail = async () => {
    setIsComponentViewerVisible(false)
    setIsLoading(true)
    try {
      const component_geometry = await fetch_component_geometry(
        { component_id: component_data._id }
      )
      // inject the geometry into the component data
      inject_geometry(component_data, component_geometry.geometry)
    } catch (error) {
      console.error('Error fetching Component Geometry:', error)
    } finally {
      setIsLoading(false)
      setIsComponentViewerVisible(true)
    }
  }
  return (
    <Sheet>
      {/* The sheet trigger with the component preview image */}
      <div className='text-left align-text-middle cursor-pointer flex items-center gap-1'>
        
          <SheetTrigger asChild>
          <div onClick={handleButtonClickComponentDetail}>
            {/* The preview image also provides a tooltip */}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className='min-w-8'>
                    <ComponentPreviewImage
                      comp_id={component_data._id}
                      alt={component_data._id}
                      width={50}
                      height={50}
                      maxHeight={50}
                    />
                  </div>
                </TooltipTrigger>
                <TooltipContent>
                  <div className='flex flex-col text-center'>
                    Click to preview this component
                    <ComponentPreviewImage
                      comp_id={component_data._id}
                      alt={component_data._id}
                      width={315}
                      height={315}
                      maxHeight={325}
                    />
                  </div>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            </div>
          </SheetTrigger>
        

        {/* The Button with the Component id */}
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Link href={`/components/${component_data._id}`}>
                <Button variant='ghost' className='text-xs h-5 w-15 hover:bg-[#009cda] hover:text-white'>
                  {component_data._id}
                </Button>
              </Link>
            </TooltipTrigger>
            <TooltipContent>
              <div className='flex flex-col text-center'>
                Click to open the component details page
              </div>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      {/* The sheet content with the component viewer */}
      <SheetContent side='bottom'>
        <SheetHeader>
          <SheetTitle className='text-center text-m'>Component Preview</SheetTitle>
          <SheetDescription>
            <p className='text-center text-sm font-bold'>{component_data._id}</p>
          </SheetDescription>
        </SheetHeader>
        {isLoading ? <ComponentViewerSkeleton message='Loading Geometry...'/> : isComponentViewerVisible && <ComponentViewer component_data={component_data} />}
        
        <SheetFooter className="flex flex-col md:flex-row items-center justify-center gap-2 mt-4 ml-2 mr-2">
          <Link href={`/components/${component_data._id}`} className="w-full md:w-200">
            <Button variant='outline' className='h-8 w-full md:w-200 hover:bg-[#009cda] hover:text-white'>
              Open Detail Page
            </Button>
          </Link>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Link href={`/findcomponent?reference_id=${component_data._id}`} className="w-full md:w-200">
                  <Button variant='outline' className='h-8 w-full md:w-200 hover:bg-[#009cda] hover:text-white'>
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

          <SheetClose asChild className="w-full md:w-200">
              <Button variant='outline' className='h-8 w-full md:w-200 hover:bg-[#009cda] hover:text-white'>
                Close Preview
              </Button>
          </SheetClose>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
