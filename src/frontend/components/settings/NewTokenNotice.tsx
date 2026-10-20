'use client'

import { useState } from 'react'
import { Check, Copy } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ONCE_NOTE } from '@/lib/accessTokens'

/**
 * A token that was just made, shown once: the text to copy, a copy button and
 * the note that it will not be shown again. The page keeps the token only in
 * the state that renders this; "Done" (or any reload) drops it.
 */
export default function NewTokenNotice({ name, token, onDone }: { name: string; token: string; onDone: () => void }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(token)
      setCopied(true)
    } catch {
      setCopied(false) // the text is selectable: the user copies it by hand
    }
  }

  return (
    <div className="space-y-2 rounded-md border border-amber-500/60 bg-amber-50 p-3 text-sm dark:bg-amber-950/30" role="status">
      <p className="font-medium">Token &quot;{name}&quot; created</p>
      <p>{ONCE_NOTE}</p>
      <div className="flex items-center gap-2">
        <code
          className="min-w-0 flex-1 select-all break-all rounded bg-background px-2 py-1.5 font-mono text-xs"
          data-testid="new-token"
        >
          {token}
        </code>
        <Button type="button" size="sm" variant="outline" onClick={copy} aria-label="Copy the token">
          {copied ? <Check className="h-4 w-4" aria-hidden /> : <Copy className="h-4 w-4" aria-hidden />}
          <span className="ml-1">{copied ? 'Copied' : 'Copy'}</span>
        </Button>
      </div>
      <Button type="button" size="sm" onClick={onDone}>Done</Button>
    </div>
  )
}
