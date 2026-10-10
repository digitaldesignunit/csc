'use client'

/**
 * The edit page (spec 3.2.2, 7.6, decision 8.123 c): the details of any
 * version of the piece --- name, notes, location, colour, the date it is
 * valid from, the capture notes and the capture fields that are still empty
 * --- edited in place. Before publish the author or moderator(D) may; after
 * it only moderator(D). A capture field that is set, the size, the quantity
 * and the fragment flag are changed by a correction.
 */
import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Camera, CalendarClock, FilePen, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import type { CatalogComponent, ComponentIdentity, ComponentSnapshot } from '@/generated/CatalogModels'
import type { SnapshotSummaryItem } from '@/generated/SnapshotModels'
import { PRECISION_LABELS } from '@/generated/Vocab'
import { DateWithPrecision, Field, VocabSelect } from '@/components/lineage/fields'
import PublicConfirmDialog from '@/components/common/PublicConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { OptionalDateInput } from '@/components/ui/optional-date-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { backendJson, isTombstone } from '@/lib/backend'
import { creditInputProblem } from '@/lib/photoCredit'
import { canSwitchPublic } from '@/lib/publicSwitch'
import { useMe } from '@/lib/me'
import {
  CAPTURE_METHOD_LABELS,
  editPatch,
  editValuesOf,
  emptyCaptureFields,
  versionLabel,
  versionToEdit,
  type EditValues,
} from '@/lib/snapshotEdit'
import { ColourField, LocationFields } from './MetadataFields'

export default function EditSnapshotForm({
  identityId,
  snapshotId,
}: {
  identityId: string
  /** `?snapshot=<sid>`: the version to open on; default the current one. */
  snapshotId?: string | null
}) {
  const router = useRouter()
  const { me, moderates } = useMe()
  const [identity, setIdentity] = useState<ComponentIdentity | null>(null)
  const [rows, setRows] = useState<SnapshotSummaryItem[] | null>(null)
  const [selected, setSelected] = useState<string | null>(snapshotId ?? null)
  const [snapshot, setSnapshot] = useState<ComponentSnapshot | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [before, setBefore] = useState<EditValues | null>(null)
  const [values, setValues] = useState<EditValues | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // the public flag belongs to the piece, not to a version: it has its own request (8.131)
  const [isPublic, setIsPublic] = useState(false)
  const [publicBusy, setPublicBusy] = useState(false)
  const [confirmPublic, setConfirmPublic] = useState(false)
  const enc = encodeURIComponent(identityId)

  // the piece and its versions, once
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const body = await backendJson<CatalogComponent | unknown>(`/identities/${enc}/compose`)
      if (isTombstone(body)) throw new Error('This component was withdrawn.')
      const list = await backendJson<SnapshotSummaryItem[]>(`/identities/${enc}/snapshots`)
      const first = versionToEdit(list, snapshotId)
      if (!first) throw new Error('This component has no version to edit.')
      if (cancelled) return
      setIdentity((body as CatalogComponent).identity)
      setIsPublic(Boolean((body as CatalogComponent).identity.is_public))
      setRows(list)
      setSelected((current) => current ?? first._id)
    }
    load().catch((err) => { if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Could not load the component') })
    return () => { cancelled = true }
  }, [enc, snapshotId])

  // the version on screen
  useEffect(() => {
    if (!selected) return
    let cancelled = false
    setSnapshot(null)
    backendJson<ComponentSnapshot>(`/snapshots/${encodeURIComponent(selected)}`)
      .then((loaded) => {
        if (cancelled) return
        const initial = editValuesOf(loaded)
        setSnapshot(loaded)
        setBefore(initial)
        setValues(initial)
        setError(null)
      })
      .catch((err) => { if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Could not load the version') })
    return () => { cancelled = true }
  }, [selected])

  const open = useMemo(() => (snapshot ? emptyCaptureFields(snapshot) : []), [snapshot])

  if (loadError) return <p role="alert" className="text-sm text-destructive">{loadError}</p>
  if (!identity || !rows || !me) {
    return <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading...</p>
  }

  const choose = (id: string) => {
    setSelected(id)
    window.history.replaceState(null, '', `/components/${enc}/edit?snapshot=${encodeURIComponent(id)}`)
  }
  const chooser = (
    <Field label="Version" htmlFor="ed-version">
      <Select value={selected ?? undefined} onValueChange={choose} disabled={busy}>
        <SelectTrigger id="ed-version" className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {[...rows].sort((a, b) => b.version - a.version).map((row) => (
            <SelectItem key={row._id} value={row._id}>{versionLabel(row, rows)}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  )
  const href = `/components/${enc}`
  if (!snapshot || !before || !values) {
    return (
      <div className="space-y-5">
        {chooser}
        <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading...</p>
      </div>
    )
  }

  const moderator = moderates(identity.dataset)
  const author = snapshot.added_by_user_id === me._id
  const status = snapshot.status
  const allowed = status === 'draft' ? author || moderator
    : status === 'pending' || status === 'published' ? moderator
      : false
  const why = allowed ? null
    : status === 'rejected' ? 'A rejected version is edited by nobody; resubmit it as a draft first.'
      : status === 'withdrawn' ? 'A withdrawn version cannot be edited.'
        : status === 'draft' ? 'Only the author or a moderator of the dataset edits a draft.'
          : 'Once a version is pending or published, a moderator of the dataset edits it.'

  const everPublished = Boolean(identity.current_snapshot_id)
    || rows.some((row) => row.status === 'published' || row.status === 'withdrawn')
  const mayChangePublic = canSwitchPublic({
    moderates: moderator,
    isCreator: identity.created_by_user_id === me._id,
    everPublished,
  })
  const changePublic = async (next: boolean) => {
    setPublicBusy(true)
    try {
      await backendJson(`/identities/${enc}`, { method: 'PATCH', body: { is_public: next } })
      setIsPublic(next)
      toast.success(next ? 'The piece is public now' : 'The piece is private now')
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not change the public flag')
    } finally {
      setPublicBusy(false)
      setConfirmPublic(false)
    }
  }
  // public asks first, private does not
  const onPublicSwitch = (next: boolean) => {
    if (next) setConfirmPublic(true)
    else void changePublic(false)
  }

  const setFields = (patch: Partial<EditValues>) => setValues((v) => (v ? { ...v, ...patch } : v))
  const capture = snapshot.capture ?? {}
  const fixed = (name: 'method' | 'device' | 'software' | 'captured_at') => !open.includes(name)
  const readOnlyHint = 'Set already: a change is recorded as a correction (Correct a version).'

  const save = async () => {
    setError(null)
    const creditProblem = creditInputProblem(values.creditText, values.creditUrl)
    if (creditProblem) {
      setError(creditProblem)
      return
    }
    const patch = editPatch(snapshot, before, values)
    if (patch === undefined) {
      setError('Latitude and longitude: two numbers within range, or both empty.')
      return
    }
    if (Object.keys(patch).length === 0) {
      router.push(href)
      return
    }
    setBusy(true)
    try {
      await backendJson(`/snapshots/${encodeURIComponent(String(snapshot._id))}`, { method: 'PATCH', body: patch })
      toast.success('Saved')
      router.push(href)
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Saving failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      {chooser}
      <p className="text-sm text-muted-foreground">
        Version {snapshot.version} ({status}). The details below are edited in place; the size, quantity and
        fragment flag, and a capture field that is set, are changed by a correction.
      </p>
      {why && (
        <p role="status" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
          {why}
        </p>
      )}
      {mayChangePublic && (
        <section aria-label="Public" className="flex items-start justify-between gap-4 rounded-md border border-border p-3">
          <div className="space-y-0.5">
            <Label htmlFor="ed-public" className="text-sm font-medium">Public</Label>
            <p className="text-xs text-muted-foreground">
              A public piece is visible to everyone without an account. It applies to the whole piece
              and takes effect at once; it needs no version change.
            </p>
          </div>
          <Switch id="ed-public" checked={isPublic} disabled={publicBusy} onCheckedChange={onPublicSwitch} />
        </section>
      )}
      <PublicConfirmDialog
        open={confirmPublic}
        onOpenChange={(open) => { if (!publicBusy) setConfirmPublic(open) }}
        title="Make this piece public?"
        subject="This piece becomes public."
        onConfirm={() => void changePublic(true)}
      />
      <fieldset disabled={!allowed || busy} className="space-y-5">
        <Field label="Name" htmlFor="ed-name">
          <Input id="ed-name" value={values.name} onChange={(event) => setFields({ name: event.target.value })}
            placeholder="Empty: the catalog number" />
        </Field>
        <Field label="Notes" htmlFor="ed-notes">
          <Textarea id="ed-notes" rows={4} maxLength={5000} value={values.notes}
            onChange={(event) => setFields({ notes: event.target.value })} />
        </Field>
        <div className="space-y-2">
          <Field label="Photo credit" htmlFor="ed-credit-text">
            <Input id="ed-credit-text" maxLength={300} value={values.creditText}
              onChange={(event) => setFields({ creditText: event.target.value })}
              placeholder="e.g. Photo: (c) Name, retrieved 2026-10-05" />
          </Field>
          <Field label="Credit link" htmlFor="ed-credit-url">
            <Input id="ed-credit-url" type="url" inputMode="url" maxLength={500} value={values.creditUrl}
              onChange={(event) => setFields({ creditUrl: event.target.value })}
              placeholder="https://... (optional)" />
          </Field>
          <p className="text-xs text-muted-foreground">
            Who all the photos of this version come from; shown under the photos. Empty: no credit.
          </p>
        </div>
        <ColourField idPrefix="ed" fields={values} setFields={setFields} />
        <LocationFields idPrefix="ed" fields={values} setFields={setFields} />

        <section className="space-y-3 border-t border-border pt-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><CalendarClock className="h-4 w-4" />Valid from</h2>
          <DateWithPrecision
            id="ed-effective"
            label="Valid from"
            at={values.effectiveFrom ? `${values.effectiveFrom}T00:00:00Z` : null}
            precision={values.precision}
            onChange={(at, precision) => setFields({ effectiveFrom: at ? at.slice(0, 10) : '', precision })}
          />
          <p className="text-xs text-muted-foreground">
            When this state starts to describe the piece ({PRECISION_LABELS[values.precision]?.toLowerCase()}). It
            keeps the order of the versions.
          </p>
        </section>

        <section className="space-y-4 border-t border-border pt-5">
          <h2 className="flex items-center gap-2 text-sm font-semibold"><Camera className="h-4 w-4" />Capture</h2>
          <Field label="Capture notes" htmlFor="ed-capture-notes">
            <Textarea id="ed-capture-notes" rows={3} maxLength={5000} value={values.captureNotes}
              onChange={(event) => setFields({ captureNotes: event.target.value })} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Method" htmlFor="ed-method" hint={fixed('method') ? readOnlyHint : undefined}>
              <VocabSelect id="ed-method" labels={CAPTURE_METHOD_LABELS} value={values.method}
                onChange={(method) => setFields({ method })} allowNone noneLabel="Not stated"
                disabled={fixed('method')} />
            </Field>
            <Field label="Device" htmlFor="ed-device" hint={fixed('device') ? readOnlyHint : undefined}>
              <Input id="ed-device" value={values.device} readOnly={fixed('device')}
                onChange={(event) => setFields({ device: event.target.value })} />
            </Field>
            <Field label="Software" htmlFor="ed-software" hint={fixed('software') ? readOnlyHint : undefined}>
              <Input id="ed-software" value={values.software} readOnly={fixed('software')}
                onChange={(event) => setFields({ software: event.target.value })} />
            </Field>
            <fieldset disabled={fixed('captured_at')} className="min-w-0">
              <OptionalDateInput id="ed-captured" label="Captured on" value={values.capturedAt}
                onChange={(value) => setFields({ capturedAt: value })} />
              {fixed('captured_at') && <p className="mt-1.5 text-xs text-muted-foreground">{readOnlyHint}</p>}
            </fieldset>
          </div>
          {(capture.markers?.length || capture.fixtures?.length || capture.coordinate_system) ? (
            <p className="text-xs text-muted-foreground">
              Markers, fixtures and the coordinate system come with the capture tool and are not edited here.
            </p>
          ) : null}
        </section>
      </fieldset>
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex flex-wrap justify-between gap-2 border-t border-border pt-4">
        <Button asChild variant="outline"><Link href={href}>Cancel</Link></Button>
        <div className="flex flex-wrap gap-2">
          {status === 'published' && !snapshot.superseded_by && (
            <Button asChild variant="outline">
              <Link href={`/components/${enc}/snapshot/new?mode=correct&snapshot=${encodeURIComponent(String(snapshot._id))}`}>
                <FilePen className="mr-2 h-4 w-4" />Correct this version
              </Link>
            </Button>
          )}
          <Button type="button" onClick={() => void save()} disabled={!allowed || busy}>
            {busy ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  )
}
