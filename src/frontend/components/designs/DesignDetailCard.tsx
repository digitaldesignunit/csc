'use client'

import { useState } from 'react'
import { DesignModel } from '@/generated/DesignModel'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { formatTimestamp, generateGrasshopperPanelXML } from '@/lib/utils'
import { Copy, Check, FileText, Edit, Trash2 } from 'lucide-react'

export default function DesignDetailCard({
  design,
  canEdit = false,
}: {
  design: DesignModel
  canEdit?: boolean
}) {
  const [copied, setCopied] = useState(false)
  const [grasshopperCopied, setGrasshopperCopied] = useState(false)

  const handleCopyToClipboard = async () => {
    try {
      const designId = design._id || design.id || ''
      await navigator.clipboard.writeText(designId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
    }
  }

  const handleCopyAsGrasshopperPanel = async () => {
    try {
      const designId = design._id || design.id || ''
      const grasshopperXML = generateGrasshopperPanelXML(designId)
      await navigator.clipboard.writeText(grasshopperXML)
      setGrasshopperCopied(true)
      setTimeout(() => setGrasshopperCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy Grasshopper panel to clipboard:', err)
    }
  }

  const designId = design._id || design.id || ''

  return (
    <Card className="w-full overflow-x-auto">
      <CardHeader className="flex items-start justify-between gap-2">
        <div className="flex items-start gap-3 flex-1 min-w-0 xl:max-w-md">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-muted-foreground mb-1">Design ID</div>
            <div className="font-mono text-sm font-medium bg-muted/50 border border-border rounded-md px-3 py-2 text-foreground break-all">
              {designId}
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
        <div className="mb-4 flex flex-col items-start justify-between gap-4 xl:flex-row">
          {/* Left side metadata */}
          <div className="w-full text-left xl:min-w-0 xl:flex-1 xl:max-w-md">
            <h2 className="mb-3 text-base font-semibold text-foreground border-b border-border pb-2">Design Information</h2>

            <div className="space-y-3">
              {/* Basic Info Section */}
              <div className="space-y-2">
                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Name</span>
                  <span className="text-xs font-semibold text-foreground bg-primary/10 px-2 py-1 rounded-md">
                    {design.name || 'Unnamed Design'}
                  </span>
                </div>
                
                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Creator</span>
                  <span className="text-xs font-semibold text-foreground bg-secondary/10 px-2 py-1 rounded-md">
                    {design.creator_username || 'Unknown'}
                  </span>
                </div>

                <div className="flex items-center justify-between p-2 bg-muted/30 rounded-lg border border-border/50">
                  <span className="text-xs font-medium text-muted-foreground">Components</span>
                  <span className="text-xs font-semibold text-foreground bg-accent/10 px-2 py-1 rounded-md">
                    {design.components.length}
                  </span>
                </div>
              </div>

              {/* Timestamps Section */}
              <div className="space-y-2">
                <h3 className="text-xs font-semibold text-foreground">Timestamps</h3>
                <div className="grid grid-cols-1 gap-2">
                  <div className="p-2 bg-muted/30 rounded-lg border border-border/50">
                    <div className="text-xs font-medium text-muted-foreground mb-1">Created</div>
                    <div className="text-xs font-mono font-semibold text-foreground">
                      {formatTimestamp(design.created)}
                    </div>
                  </div>
                  <div className="p-2 bg-muted/30 rounded-lg border border-border/50">
                    <div className="text-xs font-medium text-muted-foreground mb-1">Last Modified</div>
                    <div className="text-xs font-mono font-semibold text-foreground">
                      {formatTimestamp(design.lastmodified)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Description Section */}
              {design.description && (
                <div className="space-y-2">
                  <h3 className="text-xs font-semibold text-foreground">Description</h3>
                  <div className="p-2 bg-muted/30 rounded-lg border border-border/50">
                    <div className="text-xs text-foreground">
                      {design.description}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right side: Action buttons */}
          <div className="w-full xl:w-auto xl:flex-shrink-0">
            <h2 className="mb-3 text-base font-semibold text-foreground border-b border-border pb-2">Actions</h2>
            
            <div className="space-y-2">
              {canEdit && (
                <>
                  <Link href={`/designs/${designId}/edit`} className="block">
                    <Button variant="outline" className="w-full">
                      <Edit className="h-4 w-4 mr-2" />
                      Edit Design
                    </Button>
                  </Link>
                  
                  <Button variant="destructive" className="w-full">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete Design
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
