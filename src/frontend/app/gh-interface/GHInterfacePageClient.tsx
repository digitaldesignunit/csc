'use client'

import { useEffect, useMemo, useState } from 'react'
import Image from 'next/image'
import { useSession } from 'next-auth/react'
import { Check, ChevronDown, ClipboardCopy, Construction, Download, FileImage, Search } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Input } from '@/components/ui/input'
import { Table, TableBody, TableCell, TableRow } from '@/components/ui/table'
import {
  groupBySubcategory,
  noOutputsText,
  paragraphsOf,
  screenshotFor,
  searchComponents,
  visibleComponents,
  xmlNameOf,
  type RefComponent,
  type Reference,
} from '@/lib/ghReference'

type Props = { ghInterfaceDeactivated: boolean; screenshots: string[] }

const JUNCTION =
  'cmd /c mklink /J "%APPDATA%\\McNeel\\Rhinoceros\\8.0\\scripts\\csc_gh" "<repository>\\grasshopper_lib\\csc_gh"'
const SIGN_IN = '/auth/signin?callbackUrl=%2Fgh-interface'
const UPDATE_XML = 'DDU_CSC_Update'

/** Fetch the user object XML (open to everyone) and put it on the clipboard. */
function useCopyXml() {
  const [copied, setCopied] = useState<string | null>(null)
  const copy = async (xmlName: string) => {
    try {
      const res = await fetch(`/api/backend/ghinterface/xml/${encodeURIComponent(xmlName)}`, { credentials: 'include' })
      if (!res.ok) {
        toast.error('The component is not available to copy.')
        return
      }
      await navigator.clipboard.writeText(await res.text())
      toast.success('Copied! Paste into Grasshopper')
      setCopied(xmlName)
      window.setTimeout(() => setCopied((now) => (now === xmlName ? null : now)), 2000)
    } catch {
      toast.error('Copy to the clipboard failed.')
    }
  }
  return { copy, copied }
}

/**
 * The Grasshopper page (plan P11 stage 3, decision 8.118 C-5 as revised):
 * install first (copy CSC_Update, run it), the zip as the second way, then
 * one card per component with its screenshot, description and ports, from the
 * sources of the release.
 */
export default function GHInterfacePageClient({ ghInterfaceDeactivated, screenshots }: Props) {
  const { status } = useSession()
  const [version, setVersion] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [reference, setReference] = useState<Reference | null>(null)
  const [referenceError, setReferenceError] = useState('')
  const [query, setQuery] = useState('')
  // groups the visitor closed (all open by default; a search opens every group with a match)
  const [closed, setClosed] = useState<Set<string>>(new Set())
  const { copy, copied } = useCopyXml()

  useEffect(() => {
    if (ghInterfaceDeactivated) return
    let cancelled = false
    fetch('/api/backend/ghinterface/version', { credentials: 'include' })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (!cancelled && data) setVersion(String(data.version || '')) })
      .catch(() => undefined)
    fetch('/api/backend/ghinterface/reference', { credentials: 'include' })
      .then(async (res) => {
        if (!res.ok) throw new Error(`The reference could not be loaded (${res.status}).`)
        return (await res.json()) as Reference
      })
      .then((data) => { if (!cancelled) setReference(data) })
      .catch((err) => { if (!cancelled) setReferenceError(err instanceof Error ? err.message : 'The reference could not be loaded.') })
    return () => { cancelled = true }
  }, [ghInterfaceDeactivated])

  const download = async () => {
    setDownloading(true)
    try {
      const res = await fetch('/api/backend/ghinterface/download', { credentials: 'include' })
      if (res.status === 401 || res.status === 403) {
        toast('Sign in to download', { action: { label: 'Sign in', onClick: () => { window.location.href = SIGN_IN } } })
        return
      }
      if (!res.ok) throw new Error(`The download failed (${res.status}).`)
      const disposition = res.headers.get('content-disposition')
      const filename = disposition?.split('filename=')[1]?.replace(/"/g, '') || 'csc-grasshopper-interface.zip'
      const url = window.URL.createObjectURL(await res.blob())
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'The download failed.')
    } finally {
      setDownloading(false)
    }
  }

  const all = useMemo(() => visibleComponents(reference?.components ?? []), [reference])
  const groups = useMemo(() => groupBySubcategory(searchComponents(all, query)), [all, query])
  const shown = groups.reduce((n, g) => n + g.components.length, 0)
  const searching = query.trim().length > 0

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-3 sm:p-6">
      <div className="space-y-1">
        <h1 className="text-xl font-bold sm:text-2xl">Grasshopper</h1>
        <p className="text-sm text-muted-foreground">
          Components for Rhino 8 and Grasshopper that read from and write to the catalog: fetch components, record
          states and evidence, compute frames and descriptors.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Install and update</CardTitle></CardHeader>
        <CardContent className="space-y-4 text-sm">
          {ghInterfaceDeactivated ? (
            <p className="flex items-start gap-2 text-orange-800 dark:text-orange-200">
              <Construction className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              The interface is being updated. Downloads and updates are unavailable for the moment.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <Button type="button" size="lg" onClick={() => void copy(UPDATE_XML)} className="gap-2">
                  {copied === UPDATE_XML ? <Check className="h-4 w-4" aria-hidden /> : <ClipboardCopy className="h-4 w-4" aria-hidden />}
                  {copied === UPDATE_XML ? 'Copied! Paste into Grasshopper' : 'Copy the CSC_Update component'}
                </Button>
                <p className="min-w-0 flex-1 text-muted-foreground">
                  {version ? `Release ${version}, the one this server runs.` : 'The release this server runs.'}
                </p>
              </div>
              <ol className="list-decimal space-y-1.5 pl-5">
                <li>Open Rhino 8 and a Grasshopper definition, and paste the component onto the canvas (Ctrl+V).</li>
                <li>Switch on <b>CheckForUpdates</b> and <b>InstallUpdates</b> and run it: it installs the components
                  (UserObjects) and the shared library <code>csc_gh</code> of this release.</li>
                <li>Restart Rhino when the state says so: the library is loaded once per session.</li>
                <li>Sign in with the <b>CSC_Session</b> component before you use the others.</li>
              </ol>
              <p className="text-muted-foreground">Run CSC_Update again after a new release; it says when everything is up to date.</p>
              <div className="flex flex-wrap items-center gap-3 border-t pt-3">
                {status !== 'loading' && (
                  <Button type="button" variant="outline" onClick={() => void download()} disabled={downloading} className="gap-2">
                    <Download className="h-4 w-4" aria-hidden />
                    {downloading ? 'Downloading...' : `Download the zip${version ? ` ${version}` : ''}`}
                  </Button>
                )}
                <p className="min-w-0 flex-1 text-muted-foreground">
                  The second way (sign-in needed): all user objects and the library in one file.
                </p>
              </div>
              <details className="rounded-md border p-3">
                <summary className="cursor-pointer font-medium">Working on the library from a repository</summary>
                <div className="mt-2 space-y-2">
                  <p>
                    Link the package with a directory junction instead of installing it (no administrator rights
                    needed), then restart Rhino. CSC_Update leaves a linked package alone.
                  </p>
                  <pre className="overflow-x-auto rounded bg-muted p-2 text-xs">{JUNCTION}</pre>
                </div>
              </details>
            </>
          )}
        </CardContent>
      </Card>

      <section aria-label="Component reference" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">
            Components
            {reference && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                {searching ? `${shown} of ${all.length}` : all.length} components
              </span>
            )}
          </h2>
          <div className="relative w-full sm:w-72">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
            <Input
              type="search"
              aria-label="Search the components"
              placeholder="Search name, description or port"
              className="h-9 pl-8"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>
        {referenceError && <p role="alert" className="text-sm text-destructive">{referenceError}</p>}
        {!reference && !referenceError && <p className="text-sm text-muted-foreground">Loading...</p>}
        {reference && groups.length === 0 && (
          <Card><CardContent className="p-4 text-sm text-muted-foreground">No component matches.</CardContent></Card>
        )}
        {groups.map((group) => (
          <Collapsible
            key={group.key}
            open={searching || !closed.has(group.key)}
            onOpenChange={(open) => {
              if (searching) return
              setClosed((now) => {
                const next = new Set(now)
                if (open) next.delete(group.key)
                else next.add(group.key)
                return next
              })
            }}
            className="space-y-3"
          >
            <CollapsibleTrigger asChild>
              <button
                type="button"
                className="group flex w-full items-center justify-between gap-2 rounded-md border bg-card px-3 py-2 text-left text-base font-semibold hover:bg-accent/40"
              >
                <span>{group.key} <span className="font-normal text-muted-foreground">({group.components.length})</span></span>
                <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-data-[state=open]:rotate-180" aria-hidden />
              </button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-3">
              {group.components.map((component) => (
                <ComponentCard
                  key={component.file}
                  component={component}
                  screenshot={screenshotFor(component, screenshots)}
                  copied={copied === xmlNameOf(component)}
                  onCopy={() => void copy(xmlNameOf(component))}
                />
              ))}
            </CollapsibleContent>
          </Collapsible>
        ))}
      </section>
    </div>
  )
}

function ComponentCard({ component, screenshot, copied, onCopy }: {
  component: RefComponent
  screenshot: string | null
  copied: boolean
  onCopy: () => void
}) {
  const paragraphs = paragraphsOf(component.description)
  return (
    <Card data-component-card={component.name}>
      <CardHeader className="flex flex-col items-stretch justify-between gap-2 pb-2 sm:flex-row sm:items-start">
        <div className="min-w-0 space-y-1">
          <CardTitle className="flex flex-wrap items-center gap-x-2 gap-y-1 text-base">
            {component.name}
            {component.nickname && component.nickname !== component.name && (
              <span className="font-mono text-xs font-normal text-muted-foreground">{component.nickname}</span>
            )}
          </CardTitle>
          <Badge variant="secondary" className="font-normal">{component.subcategory}</Badge>
        </div>
        <Button
          type="button" variant="outline" size="sm" onClick={onCopy}
          aria-label="Copy Grasshopper component to clipboard" className="w-full gap-2 sm:w-auto"
        >
          {copied ? <Check className="h-4 w-4 shrink-0" aria-hidden /> : <ClipboardCopy className="h-4 w-4 shrink-0" aria-hidden />}
          {copied
            ? 'Copied! Paste into Grasshopper'
            : <><span className="sm:hidden">Copy component</span><span className="hidden sm:inline">Copy Grasshopper component to clipboard</span></>}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="relative aspect-[16/10] w-full overflow-hidden rounded-md border bg-muted/30">
            {screenshot ? (
              <Image
                src={`/gh-interface/${screenshot}`}
                alt={`${component.name} component screenshot`}
                fill
                sizes="(min-width: 768px) 40vw, 100vw"
                className="object-contain"
                unoptimized
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-1 text-center text-muted-foreground">
                <FileImage className="h-10 w-10" aria-hidden />
                <p className="text-sm font-medium">{component.name}</p>
                <p className="text-xs">Component screenshot</p>
              </div>
            )}
          </div>
          <div className="space-y-2 text-sm leading-relaxed">
            {paragraphs.length > 0
              ? paragraphs.map((p, i) => <p key={i}>{p}</p>)
              : <p className="text-muted-foreground">No description.</p>}
            {component.version && <Badge variant="outline" className="font-normal">Version {component.version}</Badge>}
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <PortTable title="Inputs" rows={component.inputs} empty="None" />
          <PortTable title="Outputs" rows={component.outputs} empty={noOutputsText(component)} />
        </div>
      </CardContent>
    </Card>
  )
}

function PortTable({ title, rows, empty }: { title: string; rows: { name: string; description: string }[]; empty: string }) {
  return (
    <div className="min-w-0 space-y-1">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.name}>
                  <TableCell className="w-0 whitespace-nowrap align-top font-mono text-xs">{row.name}</TableCell>
                  <TableCell className="whitespace-normal align-top text-sm text-muted-foreground">
                    {row.description || 'No description.'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
