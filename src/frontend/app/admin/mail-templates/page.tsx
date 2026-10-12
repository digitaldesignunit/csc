'use client'

/**
 * Mail templates (decision 8.138 e), for admins: every mail the catalog
 * sends, rendered with invented sample data. The HTML is shown in a sandboxed
 * frame (no scripts, no access to this page), light or in the dark colours,
 * at a desktop or a phone width; the plain text is the fallback a client
 * without HTML shows. "Send me a test" mails the chosen one to your own
 * address through the normal send path, and shows the reason when that fails.
 */
import { useEffect, useState } from 'react'
import { Loader2, Mail, Monitor, Moon, Send, Smartphone, Sun } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { backendJson } from '@/lib/backend'
import {
  PREVIEW_WIDTHS,
  previewHtml,
  testFailure,
  type MailPreviews,
  type PreviewScheme,
  type PreviewWidth,
} from '@/lib/mailPreview'

export default function MailTemplatesPage() {
  const [data, setData] = useState<MailPreviews | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [kind, setKind] = useState<string | null>(null)
  const [scheme, setScheme] = useState<PreviewScheme>('light')
  const [width, setWidth] = useState<PreviewWidth>('desktop')
  const [sending, setSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    backendJson<MailPreviews>('/admin/mail-templates')
      .then((body) => {
        if (cancelled) return
        setData(body)
        setKind((current) => current ?? body.mails[0]?.kind ?? null)
      })
      .catch((err) => { if (!cancelled) setError(testFailure(err)) })
    return () => { cancelled = true }
  }, [])

  const mail = data?.mails.find((m) => m.kind === kind) ?? null

  const sendTest = async () => {
    if (!mail) return
    setSending(true)
    setSendError(null)
    try {
      const sent = await backendJson<{ to: string }>(
        `/admin/mail-templates/${encodeURIComponent(mail.kind)}/test`, { method: 'POST' })
      toast.success(`Test mail sent to ${sent.to}`)
    } catch (err) {
      const reason = testFailure(err)
      setSendError(reason)
      toast.error('The test mail was not sent')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-3 sm:p-5">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
          <Mail className="h-6 w-6 text-primary" aria-hidden />Mail templates
        </h1>
        <p className="text-sm text-muted-foreground">
          Every mail the catalog sends, with invented sample data. The words are in{' '}
          <code className="rounded bg-muted px-1 text-xs">src/backend/templates/mail/</code>.
        </p>
      </div>

      {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
      {!data && !error && (
        <div className="flex justify-center py-10 text-muted-foreground"><Loader2 className="h-6 w-6 animate-spin" /></div>
      )}

      {data && (
        <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
          <nav aria-label="Mails">
            <ul className="space-y-1.5">
              {data.mails.map((entry) => (
                <li key={entry.kind}>
                  <button
                    type="button"
                    onClick={() => { setKind(entry.kind); setSendError(null) }}
                    aria-current={entry.kind === kind}
                    className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                      entry.kind === kind
                        ? 'border-primary bg-primary/5 ring-1 ring-primary/30'
                        : 'border-border bg-card hover:bg-muted/40'}`}
                  >
                    <span className="block font-medium">{entry.label}</span>
                    <span className="block text-xs text-muted-foreground">{entry.when}</span>
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          {mail && (
            <Card className="min-w-0 space-y-3 p-3 sm:p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <dl className="min-w-0 space-y-0.5 text-sm">
                  <div className="flex gap-2"><dt className="w-16 shrink-0 text-muted-foreground">Subject</dt><dd className="min-w-0 break-words font-medium">{mail.subject}</dd></div>
                  <div className="flex gap-2"><dt className="w-16 shrink-0 text-muted-foreground">Reply-To</dt><dd className="min-w-0 break-words">{mail.reply_to || 'none'}</dd></div>
                </dl>
                <Button type="button" size="sm" onClick={() => void sendTest()} disabled={sending || !data.to}
                  title={data.to ? `Sends to ${data.to}` : 'Your account has no e-mail address'}>
                  {sending ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : <Send className="mr-1.5 h-4 w-4" />}
                  Send me a test
                </Button>
              </div>
              {data.to && <p className="text-xs text-muted-foreground">The test goes to {data.to}.</p>}
              {sendError && <p className="text-sm text-destructive" role="alert">{sendError}</p>}

              <Tabs defaultValue="html">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <TabsList>
                    <TabsTrigger value="html">HTML</TabsTrigger>
                    <TabsTrigger value="text">Plain text</TabsTrigger>
                  </TabsList>
                  <div className="flex flex-wrap items-center gap-2">
                    <ToggleGroup type="single" variant="outline" size="sm" spacing={0} value={scheme}
                      onValueChange={(next) => next && setScheme(next as PreviewScheme)} aria-label="Colour scheme">
                      <ToggleGroupItem value="light" className="h-7 gap-1 px-2 text-xs"><Sun className="h-3.5 w-3.5" aria-hidden />Light</ToggleGroupItem>
                      <ToggleGroupItem value="dark" className="h-7 gap-1 px-2 text-xs"><Moon className="h-3.5 w-3.5" aria-hidden />Dark</ToggleGroupItem>
                    </ToggleGroup>
                    <ToggleGroup type="single" variant="outline" size="sm" spacing={0} value={width}
                      onValueChange={(next) => next && setWidth(next as PreviewWidth)} aria-label="Width">
                      <ToggleGroupItem value="desktop" className="h-7 gap-1 px-2 text-xs"><Monitor className="h-3.5 w-3.5" aria-hidden />Desktop</ToggleGroupItem>
                      <ToggleGroupItem value="phone" className="h-7 gap-1 px-2 text-xs"><Smartphone className="h-3.5 w-3.5" aria-hidden />Phone</ToggleGroupItem>
                    </ToggleGroup>
                  </div>
                </div>
                <TabsContent value="html" className="mt-3 overflow-x-auto rounded-md border border-border bg-muted/30 p-2">
                  <iframe
                    key={`${mail.kind}-${scheme}`}
                    title={`Preview of the mail: ${mail.label}`}
                    sandbox=""
                    srcDoc={previewHtml(mail.html, scheme)}
                    className="mx-auto block h-[42rem] max-w-full rounded border-0 bg-white"
                    style={{ width: PREVIEW_WIDTHS[width] }}
                  />
                </TabsContent>
                <TabsContent value="text" className="mt-3">
                  <pre className="max-h-[42rem] overflow-auto whitespace-pre-wrap break-words rounded-md border border-border bg-muted/30 p-3 font-mono text-xs leading-relaxed">{mail.text}</pre>
                </TabsContent>
              </Tabs>
            </Card>
          )}
        </div>
      )}
    </div>
  )
}
