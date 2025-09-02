'use client'

import { useState } from 'react'
import { componentBounds, componentColorString, hexComponentColor, generateGrasshopperPanelXML } from '@/lib/utils'
import { ComponentData } from '@/components/common/models'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import ComponentDetailMap from './ComponentDetailMap'
import { Copy, Check, FileText } from 'lucide-react'
import { useSession } from 'next-auth/react'

// Type for session user with extended properties
interface ExtendedUser {
  id?: string
  sub?: string
  username?: string | null
  name?: string | null
  email?: string | null
}

export default function ComponentDetailCard({
  component_data,
}: {
  component_data: ComponentData
}) {
  const [copied, setCopied] = useState(false)
  const [grasshopperCopied, setGrasshopperCopied] = useState(false)
  const { data: session } = useSession()

  const handleCopyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(component_data._id)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
    }
  }

  const handleCopyAsGrasshopperPanel = async () => {
    try {
      const grasshopperXML = generateGrasshopperPanelXML(component_data._id)
      await navigator.clipboard.writeText(grasshopperXML)
      setGrasshopperCopied(true)
      setTimeout(() => setGrasshopperCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy Grasshopper panel to clipboard:', err)
    }
  }

  const handleReserveComponent = async () => {
    try {
      const response = await fetch(`/api/backend/reserve/${component_data._id}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const result = await response.json()
        console.log('Component reserved successfully:', result)
        // Refresh the page to show updated reservation status
        window.location.reload()
      } else {
        const error = await response.json()
        console.error('Failed to reserve component:', error)
        // You could show a toast notification here
        alert(`Failed to reserve component: ${error.detail || 'Unknown error'}`)
      }
    } catch (err) {
      console.error('Failed to reserve component:', err)
      alert('Failed to reserve component. Please try again.')
    }
  }

  const handleReleaseComponent = async () => {
    try {
      const response = await fetch(`/api/backend/reserve/${component_data._id}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
      })

      if (response.ok) {
        const result = await response.json()
        console.log('Component released successfully:', result)
        // Refresh the page to show updated reservation status
        window.location.reload()
      } else {
        const error = await response.json()
        console.error('Failed to release component:', error)
        alert(`Failed to release component: ${error.detail || 'Unknown error'}`)
      }
    } catch (err) {
      console.error('Failed to release component:', err)
      alert('Failed to release component. Please try again.')
    }
  }

  // Component Color
  const component_color_str = componentColorString(component_data.color)
  const component_color_hex = hexComponentColor(component_data.color)

  // Component Bounds
  const component_bounds = componentBounds(component_data.bbx)

  // Lat/Lon
  const { lat, lon } = component_data.location || { lat: 37.81627937, lon: 144.95373531 }

  return (
    <Card className="w-full overflow-x-auto">
      <CardHeader className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3 flex-1 min-w-0 xl:max-w-md">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-muted-foreground mb-1">Component ID</div>
            <div className="font-mono text-sm font-medium bg-muted/50 border border-border rounded-md px-3 py-2 text-foreground break-all">
              {component_data._id}
            </div>
          </div>
          
          <div className="flex gap-1 mt-6">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopyToClipboard}
                    className="h-8 w-8 p-0 flex-shrink-0"
                  >
                    {copied ? (
                      <Check className="h-4 w-4 text-green-600" />
                    ) : (
                      <Copy className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="text-center text-sm">
                    {copied ? 'Copied!' : 'Copy ID to clipboard'}
                  </div>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopyAsGrasshopperPanel}
                    className="h-8 w-8 p-0 flex-shrink-0"
                  >
                    {grasshopperCopied ? (
                      <Check className="h-4 w-4 text-green-600" />
                    ) : (
                      <FileText className="h-4 w-4" />
                    )}
                  </Button>
                </TooltipTrigger>
                <TooltipContent>
                  <div className="text-center text-sm">
                    {grasshopperCopied ? 'Copied!' : 'Copy ID as Grasshopper Panel to clipboard'}
                  </div>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {/* Find Component Button */}
        <div className="mb-4 flex flex-col sm:flex-row gap-2">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Link href={`/findcomponent?reference_id=${component_data._id}`}>
                  <Button variant="outline" className="w-full sm:w-auto">
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

          {/* Reserve Component Button */}
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                {component_data.reserved ? (
                  // Component is reserved
                  (session?.user as ExtendedUser)?.id === component_data.reserved ? (
                    // Reserved by current user - show release button
                    <Button 
                      variant="destructive"
                      className="w-full sm:w-auto"
                      onClick={handleReleaseComponent}
                    >
                      Release Component
                    </Button>
                  ) : (
                    // Reserved by another user - show disabled button
                    <Button 
                      variant="destructive"
                      className="w-full sm:w-auto"
                      disabled
                    >
                      Reserved by {component_data.reserved_by_username || 'Another User'}
                    </Button>
                  )
                ) : (
                  // Component is available - show reserve button
                  <Button 
                    variant="default"
                    className="w-full sm:w-auto"
                    onClick={handleReserveComponent}
                  >
                    Reserve Component
                  </Button>
                )}
              </TooltipTrigger>
              <TooltipContent>
                <div className="text-center text-sm">
                  {component_data.reserved ? 
                    ((session?.user as ExtendedUser)?.id === component_data.reserved ? 
                      'Click to release this component' : 
                      `This component is reserved by ${component_data.reserved_by_username || 'another user'}`) : 
                    'Reserve this component for your project'
                  }
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        <div className="mb-4 flex flex-col items-start justify-between gap-4 xl:flex-row">
          {/* Left side metadata */}
          <div className="w-full text-left xl:min-w-0 xl:flex-1 xl:max-w-md">
            <h2 className="mb-3 text-base font-semibold text-foreground border-b border-border pb-2">Metadata</h2>

            <div className="space-y-3">
              {/* Basic Info Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Type</span>
                  <span className="text-xs font-semibold text-foreground bg-primary/10 px-2 py-1 rounded-md">
                    {component_data.type}
                  </span>
                </div>
                
                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Material</span>
                  <span className="text-xs font-semibold text-foreground bg-secondary/10 px-2 py-1 rounded-md">
                    {component_data.material}
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Color</span>
                  <div className="flex items-center gap-2">
                    <div
                      className="h-4 w-4 rounded-full border-2 border-border shadow-sm"
                      style={{ backgroundColor: component_color_hex }}
                      aria-label={`Color ${component_color_str}`}
                      title={component_color_str}
                    />
                    <span className="text-xs font-semibold text-foreground bg-accent/10 px-2 py-1 rounded-md">
                      {component_color_str}
                    </span>
                  </div>
                </div>
              </div>

              {/* Bounding Box Section */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-foreground">Bounding Box Dimensions</h3>
                <div className="grid grid-cols-3 gap-2">
                  <div className="p-2 bg-muted/30 rounded-lg border border-border/50 text-center">
                    <div className="text-xs font-medium text-muted-foreground mb-1">X</div>
                    <div className="text-xs font-mono font-semibold text-foreground">
                      {component_bounds[0].toFixed(2)}
                    </div>
                  </div>
                  <div className="p-2 bg-muted/30 rounded-lg border border-border/50 text-center">
                    <div className="text-xs font-medium text-muted-foreground mb-1">Y</div>
                    <div className="text-xs font-mono font-semibold text-foreground">
                      {component_bounds[1].toFixed(2)}
                    </div>
                  </div>
                  <div className="p-2 bg-muted/30 rounded-lg border border-border/50 text-center">
                    <div className="text-xs font-medium text-muted-foreground mb-1">Z</div>
                    <div className="text-xs font-mono font-semibold text-foreground">
                      {component_bounds[2].toFixed(2)}
                    </div>
                  </div>
                </div>
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
          <div className="w-full xl:h-[200px] xl:w-[300px] xl:flex-shrink-0">
            <h2 className="mb-3 text-base font-semibold text-foreground border-b border-border pb-2">Location</h2>
            <ComponentDetailMap lat={lat} lon={lon} />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
