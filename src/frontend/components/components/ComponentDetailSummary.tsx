'use client'

import { useState } from 'react'
import { Check, Copy, FileText } from 'lucide-react'

import type { CatalogComponent } from '@/generated/CatalogModels'
import { generateGrasshopperPanelXML } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  isConsumedShallowRow,
  isNonEmptyString,
  snapshotAddedByDisplay,
  snapshotDisplayName,
} from './componentDetailShared'

type ComponentDetailSummaryProps = {
  catalog: CatalogComponent
}

export default function ComponentDetailSummary({ catalog }: ComponentDetailSummaryProps) {
  const { identity, snapshot } = catalog
  const identityId = identity._id ?? ''
  const componentName = snapshotDisplayName(snapshot)
  const isConsumed = isConsumedShallowRow({
    consumed_at: identity.consumed_at as string | null | undefined,
  })
  const reservedBy = typeof identity.reserved === 'string' ? identity.reserved.trim() : ''
  const addedBy = snapshotAddedByDisplay(snapshot)

  const [copied, setCopied] = useState(false)
  const [grasshopperCopied, setGrasshopperCopied] = useState(false)

  const handleCopyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(identityId)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy to clipboard:', err)
    }
  }

  const handleCopyAsGrasshopperPanel = async () => {
    try {
      const grasshopperXML = generateGrasshopperPanelXML('ComponentID', identityId)
      await navigator.clipboard.writeText(grasshopperXML)
      setGrasshopperCopied(true)
      setTimeout(() => setGrasshopperCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy Grasshopper panel to clipboard:', err)
    }
  }

  return (
    <div className="w-full space-y-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h2 className="text-lg font-semibold leading-tight text-foreground break-words">
            {componentName}
          </h2>
          <p className="mt-1 font-mono text-xs text-muted-foreground break-all">{identityId}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopyToClipboard}
                  className="h-8 w-8 p-0"
                  aria-label="Copy identity ID"
                >
                  {copied ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>{copied ? 'Copied!' : 'Copy ID'}</TooltipContent>
            </Tooltip>
          </TooltipProvider>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleCopyAsGrasshopperPanel}
                  className="h-8 w-8 p-0"
                  aria-label="Copy as Grasshopper panel"
                >
                  {grasshopperCopied ? (
                    <Check className="h-4 w-4 text-green-600" />
                  ) : (
                    <FileText className="h-4 w-4" />
                  )}
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {grasshopperCopied ? 'Copied!' : 'Copy as Grasshopper panel'}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {snapshot.validated && (
          <span className="rounded-md border border-green-300 bg-green-100 px-2 py-0.5 text-[11px] font-medium text-green-800 dark:border-green-700 dark:bg-green-950/50 dark:text-green-200">
            Validated
          </span>
        )}
        {isConsumed && (
          <span className="rounded-md border border-amber-300 bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-900 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-100">
            Consumed
          </span>
        )}
        {reservedBy ? (
          <span className="rounded-md border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-foreground">
            Reserved
          </span>
        ) : null}
      </div>

      {addedBy && (
        <p className="text-xs text-muted-foreground">
          Added by <span className="font-medium text-foreground">{addedBy}</span>
        </p>
      )}

      {isNonEmptyString(snapshot.notes) && (
        <div className="rounded-md border border-border/60 bg-muted/30 px-3 py-2">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Notes
          </p>
          <p className="mt-1 text-sm whitespace-pre-wrap break-words text-foreground">
            {String(snapshot.notes)}
          </p>
        </div>
      )}
    </div>
  )
}
