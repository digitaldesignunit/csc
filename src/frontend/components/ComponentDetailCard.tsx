'use client'

import { componentBounds, componentColorString, hexComponentColor } from '@/lib/utils'
import { ComponentData } from './models'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './ui/tooltip'
import Link from 'next/link'
import { Button } from './ui/button'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from './ui/accordion'
import ComponentDetailMap from './ComponentDetailMap'

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

  return (
    <div>
      <Card className="m-2">
        <CardHeader className="flex items-start justify-between gap-2">
          <CardTitle className="text-left text-base text-foreground">
            {component_data._id}
          </CardTitle>

          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Link href={`/findcomponent?reference_id=${component_data._id}`}>
                  <Button variant="outline" className="h-8">
                    Find Component
                  </Button>
                </Link>
              </TooltipTrigger>
              <TooltipContent>
                <div className="text-center text-sm">
                  Find this component using the QR code
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </CardHeader>

        <CardContent>
          <div className="mb-4 flex flex-col items-start justify-between gap-4 md:flex-row">
            {/* Left side metadata */}
            <div className="w-full text-left md:min-w-[500px] md:w-auto">
              <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Metadata</h2>

              <div className="text-sm text-foreground">
                <div>
                  <b>Type:</b> {component_data.type}
                </div>
                <div>
                  <b>Material:</b> {component_data.material}
                </div>

                <div className="mt-1 flex items-center">
                  <span className="mr-2">
                    <b>Color:</b>
                  </span>
                  <div
                    className="h-4 w-4 shrink-0 rounded-full border border-border"
                    style={{ backgroundColor: component_color_hex }}
                    aria-label={`Color ${component_color_str}`}
                    title={component_color_str}
                  />
                  <div className="ml-2 text-sm text-muted-foreground">{component_color_str}</div>
                </div>

                <div className="mt-2">
                  <b>Bounding Box</b>
                  <ul className="list-inside list-disc text-sm">
                    <li className="ml-4">
                      <b>
                        <i>X:</i>
                      </b>{' '}
                      {component_bounds[0].toFixed(2)}
                    </li>
                    <li className="ml-4">
                      <b>
                        <i>Y:</i>
                      </b>{' '}
                      {component_bounds[1].toFixed(2)}
                    </li>
                    <li className="ml-4">
                      <b>
                        <i>Z:</i>
                      </b>{' '}
                      {component_bounds[2].toFixed(2)}
                    </li>
                  </ul>
                </div>
              </div>

              <Accordion type="single" collapsible className="mt-3 w-full">
                <AccordionItem value="item-1">
                  <AccordionTrigger>
                    <b>Show Descriptors</b>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="max-h-64 overflow-auto rounded border border-border bg-muted/40 p-2">
                      {component_data.descriptors ? (
                        <pre className="whitespace-pre-wrap text-xs text-foreground">
                          <code>{JSON.stringify(component_data.descriptors, null, 2)}</code>
                        </pre>
                      ) : (
                        <div className="text-sm text-muted-foreground">No descriptors available.</div>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="item-2">
                  <AccordionTrigger>
                    <b>Show Raw JSON</b>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="max-h-64 overflow-auto rounded border border-border bg-muted/40 p-2">
                      {component_data ? (
                        <pre className="whitespace-pre-wrap text-xs text-foreground">
                          <code>{JSON.stringify(component_data, null, 2)}</code>
                        </pre>
                      ) : (
                        <div className="text-sm text-muted-foreground">No raw JSON data available.</div>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>

            {/* Right side: small map */}
            <div className="w-full md:h-[200px] md:w-[300px]">
              <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Location</h2>
              <ComponentDetailMap lat={lat} lon={lon} />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
