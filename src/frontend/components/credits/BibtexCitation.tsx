'use client'

import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

type BibtexCitationProps = {
  bibtex: string
}

export default function BibtexCitation({ bibtex }: BibtexCitationProps) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(bibtex)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy BibTeX to clipboard:', err)
    }
  }

  return (
    <div className="relative bg-gray-200/40 rounded-md">
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={handleCopy}
              className="absolute top-2 right-2 z-10"
              aria-label="Copy BibTeX to clipboard"
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-600" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{copied ? 'Copied!' : 'Copy BibTeX'}</TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <pre className="p-4 pr-12 text-sm overflow-x-auto whitespace-pre-wrap break-words leading-relaxed font-[ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,'Liberation_Mono','Courier_New',monospace]">
        {bibtex}
      </pre>
    </div>
  )
}
