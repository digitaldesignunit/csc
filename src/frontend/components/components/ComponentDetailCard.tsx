'use client'

import { useState } from 'react'
import { componentBounds, componentColorString, hexComponentColor, generateGrasshopperPanelXML, formatTimestamp } from '@/lib/utils'
import { ExtendedComponentModel, ComponentLocation } from '@/generated/ComponentModel'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import ComponentDetailMap from './ComponentDetailMap'
import { Copy, Check, FileText, CheckCircle, Trash2, Archive, RotateCcw, ChevronDown } from 'lucide-react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import ComponentOverviewDataTableLocationCell from './overview/ComponentOverviewDataTableLocationCell'

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
  isArchived = false,
}: {
  component_data: ExtendedComponentModel
  isArchived?: boolean
}) {
  const [copied, setCopied] = useState(false)
  const [grasshopperCopied, setGrasshopperCopied] = useState(false)
  const [validating, setValidating] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [showDestructiveActions, setShowDestructiveActions] = useState(false)
  const { data: session } = useSession()
  const router = useRouter()

  const handleCopyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(component_data._id || '')
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
    }
  }

  const handleCopyAsGrasshopperPanel = async () => {
    try {
      const grasshopperXML = generateGrasshopperPanelXML('ComponentID', component_data._id || '')
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

  const handleValidateComponent = async () => {
    try {
      setValidating(true)
      const response = await fetch(`/api/backend/validate/${component_data._id}`, {
        method: 'GET',
      })
      
      if (response.ok) {
        // Redirect to validation page after successful validation
        router.push('/admin/validation')
      } else {
        console.error('Failed to validate component')
        alert('Failed to validate component. Please try again.')
      }
    } catch (error) {
      console.error('Error validating component:', error)
      alert('Failed to validate component. Please try again.')
    } finally {
      setValidating(false)
    }
  }

  const handleArchiveComponent = async () => {
    if (!confirm('Are you sure you want to archive this component? It will be removed from the main catalog but can be restored later.')) {
      return
    }

    try {
      setArchiving(true)
      const response = await fetch(`/api/backend/archive/${component_data._id}`, {
        method: 'POST',
      })

      if (response.ok) {
        // Redirect to archive page after successful archiving
        router.push('/archive/components')
      } else {
        console.error('Failed to archive component')
        alert('Failed to archive component. Please try again.')
      }
    } catch (error) {
      console.error('Error archiving component:', error)
      alert('Failed to archive component. Please try again.')
    } finally {
      setArchiving(false)
    }
  }

  const handleUnarchiveComponent = async () => {
    if (!confirm('Are you sure you want to restore this component from the archive?')) {
      return
    }

    try {
      setArchiving(true)
      const response = await fetch(`/api/backend/unarchive/${component_data._id}`, {
        method: 'POST',
      })

      if (response.ok) {
        // Redirect to the main component page after successful restoration
        router.push(`/components/${component_data._id}`)
      } else {
        console.error('Failed to restore component')
        alert('Failed to restore component. Please try again.')
      }
    } catch (error) {
      console.error('Error restoring component:', error)
      alert('Failed to restore component. Please try again.')
    } finally {
      setArchiving(false)
    }
  }

  const handleDeleteComponent = async () => {
    if (!confirm('Are you sure you want to PERMANENTLY delete this component? This action cannot be undone!')) {
      return
    }

    try {
      setDeleting(true)
      const response = await fetch(`/api/backend/components/${component_data._id}`, {
        method: 'DELETE',
      })

      if (response.ok) {
        // Redirect to components page after successful deletion
        router.push('/components')
      } else {
        console.error('Failed to delete component')
        alert('Failed to delete component. Please try again.')
      }
    } catch (error) {
      console.error('Error deleting component:', error)
      alert('Failed to delete component. Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  // Component Color
  const component_color_str = componentColorString(Array.isArray(component_data.color) ? component_data.color : [])
  const component_color_hex = hexComponentColor(Array.isArray(component_data.color) ? component_data.color : [])

  // Component Bounds
  const component_bounds = componentBounds(component_data.bbx)

  // Lat/Lon
  const { lat, lon } = component_data.location as ComponentLocation || { lat: 37.81627937, lon: 144.95373531 }

  return (
    <Card className="w-full overflow-x-auto">
      <CardHeader className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3 flex-1 min-w-0 xl:max-w-md">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-muted-foreground mb-1">Component ID</div>
            <div className="font-mono text-xs sm:text-sm font-medium bg-accent/20 border border-border rounded-md px-3 py-2 text-foreground break-all">
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
        {/* User Action Buttons */}
        <div className="mb-4 flex gap-2 xl:max-w-md">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Link href={`/findcomponent?reference_id=${component_data._id}`} className="flex-1">
                  <Button variant="outline" className="w-full">
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
                <div className="flex-1">
                  {component_data.reserved ? (
                    // Component is reserved
                    (session?.user as ExtendedUser)?.id === component_data.reserved ? (
                      // Reserved by current user - show release button
                      <Button 
                        variant="destructive"
                        className="w-full"
                        onClick={handleReleaseComponent}
                      >
                        Release Component
                      </Button>
                    ) : (
                      // Reserved by another user - show disabled button
                      <Button 
                        variant="destructive"
                        className="w-full"
                        disabled
                      >
                        Reserved by {component_data.reserved_by_username || 'Another User'}
                      </Button>
                    )
                  ) : (
                    // Component is available - show reserve button
                    <Button 
                      variant="default"
                      className="w-full"
                      onClick={handleReserveComponent}
                    >
                      Reserve Component
                    </Button>
                  )}
                </div>
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

        {/* Admin Action Buttons - Only show for admin users */}
        {session?.user?.role === 'admin' && (
          <div className="mb-4 space-y-3 xl:max-w-md">
            {/* Main Admin Actions */}
            <div className="flex gap-2">
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={handleValidateComponent}
                      disabled={validating || archiving || deleting || component_data.validated}
                      variant="default"
                      className="bg-green-600 hover:bg-green-700 flex-1"
                    >
                      {validating ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      ) : (
                        <>
                          <CheckCircle className="h-4 w-4 mr-2" />
                          <span>{component_data.validated ? 'Validated' : 'Validate'}</span>
                        </>
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <div className="text-center text-sm">
                      {component_data.validated
                        ? 'This component is already validated'
                        : 'Validate this component for public use'
                      }
                    </div>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>

              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      onClick={isArchived ? handleUnarchiveComponent : handleArchiveComponent}
                      disabled={validating || archiving || deleting}
                      variant={isArchived ? 'default' : 'outline'}
                      className="flex-1"
                    >
                      {archiving ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary"></div>
                      ) : isArchived ? (
                        <>
                          <RotateCcw className="h-4 w-4 mr-2" />
                          <span>Restore</span>
                        </>
                      ) : (
                        <>
                          <Archive className="h-4 w-4 mr-2" />
                          <span>Archive</span>
                        </>
                      )}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    <div className="text-center text-sm">
                      {isArchived
                        ? 'Restore this component to the main Catalog'
                        : 'Archive this component (can be restored later)'
                      }
                    </div>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>

            {/* Destructive Actions - Collapsible */}
            <div className="border border-destructive/30 rounded-lg overflow-hidden">
              <button
                onClick={() => setShowDestructiveActions(!showDestructiveActions)}
                className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-destructive hover:bg-destructive/10 transition-colors"
              >
                <span>Destructive Actions</span>
                <ChevronDown className={`h-4 w-4 transition-transform ${showDestructiveActions ? 'rotate-180' : ''}`} />
              </button>

              {showDestructiveActions && (
                <div className="p-3 pt-0 border-t border-destructive/30">
                  <p className="text-xs text-muted-foreground mb-2">
                    Warning: Deleting a component is permanent and cannot be undone. Consider archiving instead.
                  </p>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          onClick={handleDeleteComponent}
                          disabled={validating || archiving || deleting}
                          variant="destructive"
                          className="w-full"
                        >
                          {deleting ? (
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                          ) : (
                            <>
                              <Trash2 className="h-4 w-4 mr-2" />
                              <span>Permanently Delete</span>
                            </>
                          )}
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>
                        <div className="text-center text-sm">
                          Permanently delete this component (cannot be undone)
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="mb-4 flex flex-col items-start justify-between gap-4 xl:flex-row">
          {/* Left side metadata */}
          <div className="w-full text-left xl:min-w-0 xl:flex-1 xl:max-w-md">
            <h2 className="mb-3 text-base font-semibold text-foreground border-b border-border pb-2">Metadata</h2>

            <div className="space-y-3">
              {/* Basic Info Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Type</span>
                  <span className="text-xs font-semibold text-foreground bg-primary/25 px-2 py-1 rounded-md">
                    {component_data.type}
                  </span>
                </div>
                
                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Material</span>
                  <span className="text-xs font-semibold text-foreground bg-secondary/25 px-2 py-1 rounded-md">
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
                    <span className="text-xs font-semibold text-foreground bg-primary/25 px-2 py-1 rounded-md">
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

              {/* Additional Info Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Dataset</span>
                  <span className="text-xs font-semibold text-foreground bg-secondary/25 px-2 py-1 rounded-md">
                    {component_data.dataset}
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Fragment</span>
                  <span className="text-xs font-semibold text-foreground bg-primary/25 px-2 py-1 rounded-md">
                    {String(component_data.fragment)}
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Complexity</span>
                  <span className="text-xs font-semibold text-foreground bg-secondary/25 px-2 py-1 rounded-md">
                    {component_data.complexity}
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Location</span>
                  <span className="text-xs font-semibold text-foreground bg-primary/25 px-2 py-1 rounded-md max-w-[60%] truncate">
                    <ComponentOverviewDataTableLocationCell coords={component_data.location as ComponentLocation} showTooltip={false} />
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Created</span>
                  <span className="text-xs font-semibold text-foreground bg-secondary/25 px-2 py-1 rounded-md">
                    {formatTimestamp(component_data.created)}
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Last Modified</span>
                  <span className="text-xs font-semibold text-foreground bg-primary/25 px-2 py-1 rounded-md">
                    {formatTimestamp(component_data.lastmodified)}
                  </span>
                </div>

                {/* Reserved state is already shown via action buttons; omit duplicate here */}
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
