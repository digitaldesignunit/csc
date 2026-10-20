'use client'

import Link from 'next/link'
import { Loader2, ShieldAlert, ShieldCheck } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { WriteButton } from '@/components/ui/write-button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ACCESS_LINE, LOOPBACK_WARNING, allowText, type ConsentView } from '@/lib/oauthConsent'

/**
 * What the consent page draws (decision 8.168 b): the host Allow sends the
 * browser to, large; the name the tool gives itself, small and marked as
 * unchecked; the access; Allow and Deny. Without the right role only a refusal
 * and Deny. Presentation only, so the unit test renders it.
 */
export default function ConsentCard({
  view,
  problem,
  busy,
  leaving,
  onAllow,
  onDeny,
}: {
  view: ConsentView | null
  problem: string | null
  busy: boolean
  leaving: string | null
  onAllow: () => void
  onDeny: () => void
}) {
  return (
    <div className="flex min-h-[70vh] items-start justify-center p-4 pt-8 sm:items-center">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mb-2 flex justify-center">
            {view && !view.can_allow
              ? <ShieldAlert className="h-10 w-10 text-amber-600" aria-hidden />
              : <ShieldCheck className="h-10 w-10 text-primary" aria-hidden />}
          </div>
          <CardTitle className="text-xl">Connect a tool to the catalog</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          {!view && !problem && (
            <p className="flex items-center justify-center gap-2 text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />Loading...
            </p>
          )}
          {problem && <p className="text-center text-destructive" role="alert">{problem}</p>}
          {leaving !== null && (
            <p className="text-center text-muted-foreground" role="status">Returning to {leaving}...</p>
          )}
          {view && leaving === null && (
            <>
              <div className="space-y-1 text-center">
                <p className="text-muted-foreground">You will be sent back to</p>
                <p className="break-all text-2xl font-bold" data-testid="redirect-host">{view.redirect_host}</p>
                {view.client_name && (
                  <p className="text-xs text-muted-foreground">
                    The tool calls itself &quot;{view.client_name}&quot;. It chose that name; it is not checked.
                  </p>
                )}
              </div>
              {view.redirect_is_loopback && (
                <p className="rounded-md border border-amber-500/60 bg-amber-50 p-2 text-xs dark:bg-amber-950/30" role="alert">
                  {LOOPBACK_WARNING}
                </p>
              )}
              <div className="rounded-md border p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Access</p>
                <p className="font-medium">{view.access || ACCESS_LINE}</p>
              </div>
              {view.can_allow ? (
                <>
                  <p className="text-xs text-muted-foreground">{allowText(view.redirect_host)}</p>
                  <div className="flex gap-2">
                    <WriteButton className="flex-1" disabled={busy} onClick={onAllow}>Allow</WriteButton>
                    <WriteButton className="flex-1" variant="outline" disabled={busy} onClick={onDeny}>Deny</WriteButton>
                  </div>
                </>
              ) : (
                <>
                  <p className="text-center text-destructive" role="alert">{view.refusal}</p>
                  <div className="flex gap-2">
                    <WriteButton className="flex-1" variant="outline" disabled={busy} onClick={onDeny}>Deny</WriteButton>
                    <Button asChild variant="ghost" className="flex-1"><Link href="/my-work">Back to the catalog</Link></Button>
                  </div>
                </>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
