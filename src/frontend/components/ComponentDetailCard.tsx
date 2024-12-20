'use client'

import { componentBounds, componentColorString, hexComponentColor } from '@/lib/utils'
import { ComponentData } from './models'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from './ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip'
import Link from 'next/link'
import { Button } from './ui/button'


export default function ComponentDetailCard({
  component_data,
}: {
  component_data: ComponentData
}) {
   // Component Color
    const component_color_str = componentColorString(component_data.color)
    const component_color_hex = hexComponentColor(component_data.color)
  
    // Component Bounds
    const component_bounds = componentBounds(component_data.bbx)
  return (
    <div>
      <Card className='m-2'>
        <CardHeader>
          <CardTitle className='text-sm text-left'>{component_data._id}</CardTitle>
        </CardHeader>       
        
        <CardContent className='text-left'>

        <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Link href={`/findcomponent?reference_id=${component_data._id}`}>
                  <Button variant='outline' className='h-8 hover:bg-[#009cda] hover:text-white'>
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
          
          <div>
            Type: {component_data.type} <br/>
            Material: {component_data.material} <br/>
            X: {component_bounds[0].toFixed(2)} | Y: {component_bounds[1].toFixed(2)} | Z: {component_bounds[2].toFixed(2)}<br/>
            <div className='flex items-center max-w-12 mb-4'>
              Color: 
              <div className='ml-2 avatar rounded-full min-h-4 min-w-4 max-w-5 max-h-5 items-center justify-left' style={{backgroundColor: component_color_hex}}></div>
              <div className='ml-2 items-center justify-center text-center'>{component_color_str}</div>
            </div>
          </div>

        </CardContent>
      </Card>
    </div>
  )
}