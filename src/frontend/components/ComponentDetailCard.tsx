'use client'

import { componentBounds, componentColorString, hexComponentColor } from '@/lib/utils'
import { ComponentData } from './models'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip'
import Link from 'next/link'
import { Button } from './ui/button'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from './ui/accordion'

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

  // Lat/Lon
  const { lat, lon } = component_data.location || { lat: 37.81627937, lon: 144.95373531 }
  const mapSrc = `https://maps.google.com/maps?q=${lat},${lon}&z=15&output=embed`

  return (
    <div>
      <Card className='m-2'>
        <CardHeader className='flex items-center justify-between'>
          <CardTitle className='text-sm text-left'>{component_data._id}</CardTitle>

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
        </CardHeader>

        <CardContent>
          <div className='flex flex-col md:flex-row justify-between items-start gap-4 mb-4'>
            {/* Left side metadata */}
            <div className='text-left w-full md:min-w-[500px] md:w-auto'>
              <h2 className='font-bold mb-2'>Metadata</h2>
              <div><b>Type:</b> {component_data.type}</div>
              <div><b>Material:</b> {component_data.material}</div>
              <div className='flex items-center'>
                <span><b>Color:</b></span>
                <div
                  className='ml-2 avatar rounded-full min-h-4 min-w-4 max-w-5 max-h-5'
                  style={{ backgroundColor: component_color_hex }}
                ></div>
                <div className='ml-2'>{component_color_str}</div>
              </div>
              <div>
                <b>BoundingBox</b><br />
                <ul className='list-disc list-inside'>
                  <li className='ml-4'><b><i>X:</i></b> {component_bounds[0].toFixed(2)}</li>
                  <li className='ml-4'><b><i>Y:</i></b> {component_bounds[1].toFixed(2)}</li>
                  <li className='ml-4'><b><i>Z:</i></b> {component_bounds[2].toFixed(2)}</li>
                </ul>
              </div>

              <Accordion type="single" collapsible className="w-full mt-2">
                <AccordionItem value="item-1">
                  <AccordionTrigger><b>Show Descriptors</b></AccordionTrigger>
                  <AccordionContent>
                    <div className="max-h-64 overflow-auto p-2 bg-gray-50 border border-gray-300 rounded">
                      {component_data.descriptors ? (
                        <pre className='text-sm whitespace-pre-wrap'>
                          <code>
                            {JSON.stringify(component_data.descriptors, null, 2)}
                          </code>
                        </pre>
                      ) : (
                        <div>No descriptors available.</div>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="item-2">
                  <AccordionTrigger><b>Show Raw JSON</b></AccordionTrigger>
                  <AccordionContent>
                    <div className="max-h-64 overflow-auto p-2 bg-gray-50 border border-gray-300 rounded">
                      {component_data ? (
                        <pre className='text-sm whitespace-pre-wrap'>
                          <code>
                            {JSON.stringify(component_data, null, 2)}
                          </code>
                        </pre>
                      ) : (
                        <div>No raw JSON data available.</div>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>

            {/* Right side: small Google Maps embed */}
            <div className='w-full md:w-[300px] md:h-[200px]'>
              <h2 className='font-bold mb-2'>Location</h2>
              <iframe
                width="100%"
                height="200"
                style={{ border: 0 }}
                src={mapSrc}
                allowFullScreen
                aria-hidden="false"
                tabIndex={0}
                className='rounded-md overflow-hidden'
              ></iframe>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
