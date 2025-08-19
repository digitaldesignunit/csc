'use client'

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@radix-ui/react-tooltip"
import { CircleHelp } from "lucide-react"

export default function ComponentOverviewDataTableHeader({
  header
} : {
  header: string
}) {
  return (
    <div className='flex flex-row text-left gap-1 whitespace-nowrap'>
      <div>{header}</div>
      <TooltipProvider>
        <Tooltip>

          <TooltipTrigger asChild>
            <CircleHelp size={14}/>
          </TooltipTrigger>

          <TooltipContent>
            <div className='text-center bg-accent-foreground rounded-sm p-2 border'>
              {header}
            </div>
          </TooltipContent>

        </Tooltip>
      </TooltipProvider>
    </div>
  )
}
