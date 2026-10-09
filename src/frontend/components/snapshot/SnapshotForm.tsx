'use client'

/**
 * The one snapshot form (spec 7.6, decisions 7.5, 8.87): new component, cut
 * from pieces, record new state, correct. Steps: tag or parents, details,
 * size (an authored box), photos, optional inspection (new component), then
 * review and submit. Submitting is draft --> photos --> submit, for every
 * role: nobody publishes directly (8.120), a moderator of the dataset
 * publishes it from the queue (also their own).
 * Nothing is lost when a later step fails: the draft exists and the form
 * resumes from the step that failed.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, PackagePlus } from 'lucide-react'

import type { DatasetView } from '@/generated/AccessModels'
import type { CatalogComponent, CatalogRow, ComponentSnapshot } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { ORIGINAL_FUNCTION_LABELS, type OriginalFunction } from '@/generated/Vocab'
import SnapshotPhotoCapture from '@/components/photos/SnapshotPhotoCapture'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/lineage/fields'
import { backendJson, isTombstone } from '@/lib/backend'
import { cleanOrigin, useMaterials } from '@/lib/lineage'
import { useMe } from '@/lib/me'
import { uuidFromScan } from '@/lib/scanIds'
import { uploadSnapshotPhoto } from '@/lib/snapshotPhotos'
import {
  MODE_TITLES,
  authoredBox,
  boxDimensionsOf,
  canonicalizeBoxAxesMm,
  emptyFields,
  identityBody,
  isAuthoredBoxOnly,
  keptGeometry,
  problemsOf,
  snapshotBody,
  validDimensions,
  type FormMode,
  type Problem,
} from '@/lib/snapshotForm'
import { DetailsStep } from './DetailsStep'
import { ParentTags } from './ParentTags'
import { PositionedEvidence, usePositionedEvidence } from './PositionedEvidence'
import { SizeStep } from './SizeStep'
import { TagField } from './TagField'
import type { FormValues } from './types'

type StepId = 'tag' | 'parents' | 'details' | 'size' | 'photos' | 'inspection' | 'review'

const STEP_LABELS: Record<StepId, string> = {
  tag: 'Tag',
  parents: 'Parents',
  details: 'Details',
  size: 'Size',
  photos: 'Photos',
  inspection: 'Inspection',
  review: 'Review',
}

/** The step each problem belongs to. */
const PROBLEM_STEP: Record<string, StepId> = {
  tag: 'tag',
  parents: 'parents',
  dataset: 'details',
  original_function: 'details',
  material: 'details',
  location: 'details',
  quantity: 'details',
  effective_on: 'details',
  size: 'size',
}

export type SnapshotFormProps = {
  mode: FormMode
  /** New / cut: the id of the scanned, unused tag. */
  tag?: string
  /** Cut: parents to start with. */
  parents?: string[]
  /** State / correct: the component. */
  identityId?: string
  /** Correct: the published snapshot to correct. */
  snapshotId?: string
}

type Done = { identityId: string; snapshotId: string; status: string }
type Progress = { identityId: string; snapshotId: string; photosUploaded: number; submitted: string | null }

const AVAILABILITY = '/component_id_transmission/availability'

function stepsOf(props: SnapshotFormProps): StepId[] {
  switch (props.mode) {
    case 'new': return [...(props.tag ? [] : ['tag' as const]), 'details', 'size', 'photos', 'inspection', 'review']
    case 'cut': return ['parents', 'details', 'size', 'photos', 'review']
    default: return ['details', 'size', 'photos', 'review']
  }
}

function initialValues(props: SnapshotFormProps): FormValues {
  return {
    tag: props.tag ?? '',
    parents: props.parents ?? [],
    dataset: '',
    originalFunction: null,
    material: '',
    tradeName: '',
    origin: null,
    fields: emptyFields(),
    dims: ['', '', ''],
    sizeEntered: props.mode !== 'correct',
    photos: [],
    inspect: false,
  }
}

/** Values of the version on screen, for a new state or a correction. */
function valuesOf(mode: FormMode, catalog: CatalogComponent): FormValues {
  const snapshot = primarySnapshot(catalog) as ComponentSnapshot
  const color = Array.isArray(snapshot.color) && snapshot.color.length === 3
    ? (snapshot.color.map((v) => Math.round(v)) as [number, number, number])
    : emptyFields().color
  const dims = boxDimensionsOf(snapshot.geometry as never)
  return {
    ...initialValues({ mode }),
    dataset: catalog.identity.dataset,
    originalFunction: catalog.identity.original_function as OriginalFunction,
    fields: {
      ...emptyFields(),
      name: snapshot.name ?? '',
      notes: snapshot.notes ?? '',
      color,
      lat: snapshot.location ? String(snapshot.location.lat) : '',
      lon: snapshot.location ? String(snapshot.location.lon) : '',
      quantity: snapshot.quantity ?? 1,
      fragment: snapshot.fragment ?? false,
    },
    dims: dims ?? ['', '', ''],
  }
}

export default function SnapshotForm(props: SnapshotFormProps) {
  const { mode } = props
  const { me, moderates, loading: meLoading } = useMe()
  const materials = useMaterials()
  const [datasets, setDatasets] = useState<DatasetView[] | null>(null)
  const [datasetsError, setDatasetsError] = useState<string | null>(null)
  const [datasetsAttempt, setDatasetsAttempt] = useState(0)
  const [catalog, setCatalog] = useState<CatalogComponent | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [parentRow, setParentRow] = useState<CatalogRow | null>(null)
  const [parentRead, setParentRead] = useState(false)
  // a draw (8.105): the only parent is a batch; `remaining` is derived by the backend
  const [batch, setBatch] = useState<{ id: string; size: number; remaining: number } | null>(null)
  const sizeOffered = useRef(false)
  // once the user picks a dataset the default never overrides it
  const datasetTouched = useRef(false)
  const [values, setValues] = useState<FormValues>(() => initialValues(props))
  const drawsRest = batch !== null && Number(values.fields.quantity) >= batch.remaining
  const [seeded, setSeeded] = useState(mode === 'new' || mode === 'cut')
  const steps = useMemo(() => stepsOf({ mode, tag: props.tag }), [mode, props.tag])
  const [step, setStep] = useState<StepId>(steps[0])
  const [tagState, setTagState] = useState<{ tag: string; message: string | null; ok: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<Done | null>(null)
  const progress = useRef<Progress | null>(null)
  const topRef = useRef<HTMLDivElement>(null)

  const set = useCallback((patch: Partial<FormValues>) => setValues((v) => ({ ...v, ...patch })), [])
  const setFields = useCallback(
    (patch: Partial<FormValues['fields']>) => setValues((v) => ({ ...v, fields: { ...v.fields, ...patch } })),
    [],
  )

  // DATA ---------------------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    setDatasetsError(null)
    backendJson<DatasetView[]>('/datasets')
      .then((rows) => { if (!cancelled) setDatasets(rows.filter((d) => d.roles.includes('contributor'))) })
      .catch((err) => {
        // not "you contribute to no dataset": the list could not be read
        if (!cancelled) setDatasetsError(err instanceof Error ? err.message : 'The datasets could not be loaded')
      })
    return () => { cancelled = true }
  }, [datasetsAttempt])

  const { identityId: wantedIdentity, snapshotId: wantedSnapshot } = props
  useEffect(() => {
    if (mode !== 'state' && mode !== 'correct') return
    if (!wantedIdentity) return
    let cancelled = false
    const query = mode === 'correct' && wantedSnapshot
      ? `?${new URLSearchParams({ snapshots: wantedSnapshot })}` : ''
    backendJson<CatalogComponent | unknown>(`/identities/${encodeURIComponent(wantedIdentity)}/compose${query}`)
      .then((body) => {
        if (cancelled) return
        if (isTombstone(body)) {
          setLoadError('This component was withdrawn.')
          return
        }
        const passport = body as CatalogComponent
        setCatalog(passport)
        setValues(valuesOf(mode, passport))
        setSeeded(true)
      })
      .catch((err) => { if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Could not load the component') })
    return () => { cancelled = true }
  }, [mode, wantedIdentity, wantedSnapshot])

  // a cut starts in the dataset of its first parent, and stands if it does
  const firstParent = values.parents[0] ?? null
  useEffect(() => {
    if (mode !== 'cut') return
    if (!firstParent) {
      setParentRow(null)
      setParentRead(false)
      return
    }
    let cancelled = false
    setParentRead(false)
    backendJson<CatalogRow>(`/identities/${encodeURIComponent(firstParent)}?expand=shallow`)
      .then((row) => { if (!cancelled) { setParentRow(row); setParentRead(true) } })
      .catch(() => { if (!cancelled) { setParentRow(null); setParentRead(true) } })
    return () => { cancelled = true }
  }, [mode, firstParent])

  const soleParent = values.parents.length === 1 ? firstParent : null
  const batchSize = parentRow && soleParent === parentRow._id ? (parentRow.quantity ?? 1) : 1
  useEffect(() => {
    if (mode !== 'cut' || !soleParent || batchSize <= 1) {
      setBatch(null)
      return
    }
    let cancelled = false
    backendJson<{ remaining?: number | null }>(`/identities/${encodeURIComponent(soleParent)}?expand=none`)
      .then((body) => {
        if (cancelled) return
        if (typeof body.remaining === 'number') {
          setBatch({ id: soleParent, size: batchSize, remaining: body.remaining })
          // the batch's proxy describes each piece: a size of its own is the exception
          if (!sizeOffered.current) {
            sizeOffered.current = true
            setValues((v) => ({ ...v, sizeEntered: false }))
          }
        } else {
          setBatch(null)
        }
      })
      .catch(() => { if (!cancelled) setBatch(null) })
    return () => { cancelled = true }
  }, [mode, soleParent, batchSize])

  // The default dataset: the first parent's when it is one the user contributes
  // to, else the first of theirs. A cut waits for its parent when the link names
  // one, and takes the parent's dataset when the parent is named later, as long
  // as the user has not chosen (review finding 1 of the P9 frontend fixes).
  useEffect(() => {
    if (!datasets || datasets.length === 0 || datasetTouched.current) return
    if (mode !== 'new' && mode !== 'cut') return
    if (mode === 'cut' && firstParent && !parentRead) return
    const preferred = parentRow && datasets.some((d) => d._id === parentRow.dataset) ? parentRow.dataset : datasets[0]._id
    setValues((v) => (v.dataset === preferred ? v : { ...v, dataset: preferred }))
  }, [datasets, mode, parentRow, parentRead, firstParent])

  // the tag must be free (new and cut)
  const tagId = uuidFromScan(values.tag)
  useEffect(() => {
    if (mode !== 'new' && mode !== 'cut') return
    if (!tagId) return
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      backendJson<{ available: boolean; conflict: 'identity' | 'snapshot' | null }>(
        `${AVAILABILITY}/${encodeURIComponent(tagId)}`, { signal: controller.signal })
        .then((res) => setTagState({
          tag: tagId,
          ok: res.available,
          message: res.available ? 'This tag is free for a new component.'
            : res.conflict === 'snapshot' ? 'This id is a snapshot id; use the id printed on the tag.'
              : 'A component with this tag already exists.',
        }))
        .catch((err) => {
          if ((err as { name?: string })?.name === 'AbortError') return
          setTagState({ tag: tagId, ok: false, message: 'Could not check the tag.' })
        })
    }, 250)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [mode, tagId])
  const tagFree = tagId !== null && tagState?.tag === tagId ? tagState : null

  // CHECKS -------------------------------------------------------------------
  const identity = catalog?.identity ?? null
  const snapshot = catalog ? (primarySnapshot(catalog) as ComponentSnapshot) : null
  const function_ = values.originalFunction ?? (parentRow?.original_function as string | undefined) ?? identity?.original_function
  const column = function_ === 'IfcColumn'
  const authoredOnly = snapshot ? isAuthoredBoxOnly(snapshot.geometry as never) : false
  const currentSize = snapshot ? boxDimensionsOf(snapshot.geometry as never) : null
  const scanned = mode === 'correct' && !!snapshot && !authoredOnly

  const problems: Problem[] = useMemo(() => problemsOf({
    mode,
    fields: values.fields,
    identity: {
      tag: tagId ?? '',
      dataset: values.dataset,
      parents: values.parents,
      originalFunction: values.originalFunction,
      material: values.material,
      tradeName: values.tradeName,
      origin: values.origin,
    },
    dimensions: values.dims,
    sizeEntered: values.sizeEntered,
    draw: batch ? { remaining: batch.remaining } : undefined,
  }), [mode, values, tagId, batch])

  const stepProblems = (id: StepId): Problem[] => {
    const own = problems.filter((p) => PROBLEM_STEP[p.field] === id)
    if (id === 'tag' && !tagFree?.ok && !own.some((p) => p.field === 'tag')) {
      own.push({ field: 'tag', message: tagFree?.message ?? 'Checking the tag...' })
    }
    if (id === 'parents' && values.tag.trim() && !tagId) {
      own.push({ field: 'tag', message: 'The tag of the new piece is not an id.' })
    }
    if (id === 'parents' && tagId && tagFree && !tagFree.ok) own.push({ field: 'tag', message: tagFree.message ?? '' })
    // a tag that came with the link is checked on the first step
    if (id === 'details' && mode === 'new' && props.tag && tagFree && !tagFree.ok) {
      own.push({ field: 'tag', message: tagFree.message ?? '' })
    }
    return own
  }

  const positioned = usePositionedEvidence(
    identity?._id ?? '', snapshot ? String(snapshot._id) : '', mode === 'correct' && values.sizeEntered && !!snapshot)

  // NAVIGATION ---------------------------------------------------------------
  const index = steps.indexOf(step)
  const go = (next: StepId) => {
    setStep(next)
    topRef.current?.scrollIntoView({ block: 'start' })
  }
  const next = () => { if (steps[index + 1]) go(steps[index + 1]) }
  const back = () => { if (steps[index - 1]) go(steps[index - 1]) }
  const blocking = stepProblems(step)

  // SUBMIT -------------------------------------------------------------------
  const geometry = () => {
    if (batch && !values.sizeEntered) return undefined // the server copies the batch's proxy
    if (mode === 'correct' && !values.sizeEntered) return keptGeometry((snapshot as ComponentSnapshot).geometry as never)
    const dims = validDimensions(...values.dims) as [number, number, number]
    return authoredBox(dims[0], dims[1], dims[2], column)
  }

  const submit = async () => {
    const all = problems
    if (all.length > 0) {
      setError(all[0].message)
      const target = PROBLEM_STEP[all[0].field]
      if (target && steps.includes(target)) go(target)
      return
    }
    if (mode === 'correct' && scanned) return
    setBusy(true)
    setError(null)
    try {
      if (!progress.current) {
        const body = snapshotBody(values.fields, geometry(), { inheritDate: mode === 'correct' })
        if (mode === 'new' || mode === 'cut') {
          const created = await backendJson<{ identity: { _id: string }; snapshot: { _id: string } }>('/identities', {
            method: 'POST',
            body: identityBody({
              tag: tagId ?? '',
              dataset: values.dataset,
              parents: values.parents,
              originalFunction: values.originalFunction,
              material: values.material,
              tradeName: values.tradeName,
              origin: values.origin ? cleanOrigin(values.origin) : null,
            }, body),
          })
          progress.current = { identityId: created.identity._id, snapshotId: created.snapshot._id, photosUploaded: 0, submitted: null }
        } else if (mode === 'state') {
          const created = await backendJson<{ _id: string; identity_id: string }>(
            `/identities/${encodeURIComponent(identity!._id)}/snapshots`, { method: 'POST', body })
          progress.current = { identityId: created.identity_id, snapshotId: created._id, photosUploaded: 0, submitted: null }
        } else {
          const created = await backendJson<{ _id: string; identity_id: string }>(
            `/snapshots/${encodeURIComponent(String(snapshot!._id))}/supersede`, { method: 'POST', body })
          progress.current = { identityId: created.identity_id, snapshotId: created._id, photosUploaded: 0, submitted: null }
        }
      }
      const run = progress.current
      // photo i goes to slot i: a retry overwrites, it never doubles
      for (let i = run.photosUploaded; i < values.photos.length; i += 1) {
        await uploadSnapshotPhoto(run.snapshotId, i, values.photos[i])
        run.photosUploaded = i + 1
      }
      if (!run.submitted) {
        const result = await backendJson<{ status?: string }>(
          `/snapshots/${encodeURIComponent(run.snapshotId)}/submit`, { method: 'POST' })
        run.submitted = result?.status ?? 'pending'
      }
      if ((mode === 'new' || mode === 'cut') && tagId) {
        // clears the id queued for Grasshopper, when there is one
        await backendJson('/component_id_transmission/consume', {
          method: 'POST', body: { identity_id: tagId } }).catch(() => undefined)
      }
      setDone({ identityId: run.identityId, snapshotId: run.snapshotId, status: run.submitted })
    } catch (err) {
      const where = progress.current
        ? progress.current.photosUploaded < values.photos.length ? 'Uploading the photos failed'
          : 'Submitting failed'
        : 'Recording failed'
      setError(`${where}: ${err instanceof Error ? err.message : 'unknown error'}`)
    } finally {
      setBusy(false)
    }
  }

  // RENDER -------------------------------------------------------------------
  const title = MODE_TITLES[mode]
  if (loadError) {
    return <p role="alert" className="text-sm text-destructive">{loadError}</p>
  }
  if (datasetsError) {
    return (
      <div role="alert" className="space-y-3">
        <p className="text-sm text-destructive">Your datasets could not be loaded: {datasetsError}</p>
        <Button type="button" variant="outline" size="sm" onClick={() => { setDatasetsError(null); setDatasetsAttempt((n) => n + 1) }}>
          Try again
        </Button>
      </div>
    )
  }
  const creating = mode === 'new' || mode === 'cut'
  const waitingForDefault = creating && datasets !== null && datasets.length > 0 && !values.dataset
  if (!seeded || datasets === null || meLoading || waitingForDefault) {
    return <p className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />Loading...</p>
  }
  if (!me) {
    return <p className="text-sm text-muted-foreground">Sign in to record components.</p>
  }

  if (done) {
    return (
      <section className="space-y-4" aria-live="polite">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <CheckCircle2 className="h-5 w-5 text-green-600" />
          Recorded and submitted
        </h2>
        <p className="text-sm text-muted-foreground">
          Submitted: a moderator of the dataset publishes it; until then only you and the moderators see it.
          {mode === 'cut' && !batch ? ' The parents leave circulation when it is published.' : ''}
          {batch
            ? (drawsRest
              ? ' Publishing it draws the rest of the batch: the batch then leaves circulation as split.'
              : ' The batch stays in circulation while pieces remain.')
            : ''}
        </p>
        {mode === 'new' && values.inspect && (
          <p className="text-sm text-muted-foreground">
            You asked for a visual inspection: evidence is recorded about a published state, so open the
            component and add it once a moderator has published it (Add evidence, visual inspection).
          </p>
        )}
        {mode === 'correct' && values.sizeEntered && identity && positioned && (
          <PositionedEvidence identityId={identity._id} records={positioned} />
        )}
        <div className="flex flex-wrap gap-2">
          <Button asChild>
            <Link href={`/components/${done.identityId}`}>Open the component</Link>
          </Button>
        </div>
      </section>
    )
  }

  const dims = validDimensions(...values.dims)
  const boxText = dims
    ? (() => {
      const { xMm, yMm, zMm } = canonicalizeBoxAxesMm(dims[0], dims[1], dims[2], column)
      return `${xMm.toFixed(1)} x ${yMm.toFixed(1)} x ${zMm.toFixed(1)}`
    })()
    : null
  const moderator = moderates(values.dataset || identity?.dataset)
  const rgb = values.fields.color

  return (
    <div className="space-y-6" ref={topRef}>
      <nav aria-label={`${title} progress`}>
        <p className="text-sm font-medium md:hidden">
          Step {index + 1} of {steps.length} - {STEP_LABELS[step]}
        </p>
        <div className="hidden flex-wrap gap-2 md:flex">
          {steps.map((s, i) => (
            <Badge key={s} variant={s === step ? 'default' : i < index ? 'secondary' : 'outline'} className="px-3 py-1">
              {i + 1}. {STEP_LABELS[s]}
            </Badge>
          ))}
        </div>
      </nav>

      {scanned && (
        <p role="status" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
          This version comes from a scan. A correction from the web copies only an authored box, not
          scan files, so it is not offered here: name, notes, location and colour are edited in place
          (Edit details), and a wrong scan is corrected with Grasshopper.
        </p>
      )}

      {step === 'tag' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Tag of the new piece</h2>
            <p className="text-sm text-muted-foreground">
              Scan the QR code on the piece, or paste its id. The id must not be in the catalog yet.
            </p>
          </div>
          <TagField id="sf-tag" value={values.tag} onChange={(tag) => set({ tag })} autoScan />
          {tagId && (
            <p className={`text-xs ${tagFree?.ok ? 'text-green-700 dark:text-green-400' : tagFree ? 'text-destructive' : 'text-muted-foreground'}`}>
              {tagFree?.message ?? 'Checking the tag...'}
              {tagFree && !tagFree.ok && tagFree.message?.startsWith('A component') && (
                <> <Link href={`/components/${tagId}`} className="underline underline-offset-4">Open it</Link></>
              )}
            </p>
          )}
        </section>
      )}

      {step === 'parents' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Cut from pieces</h2>
            <p className="text-sm text-muted-foreground">
              Scan the tag of the piece it was cut from. Add more than one to record a merge. The parents leave
              circulation once the new piece is published. From a batch of identical pieces you draw pieces
              instead: the batch stays in circulation.
            </p>
            {batch && (
              <p role="status" className="text-sm font-medium">
                Batch: {batch.size} recorded, {batch.size - batch.remaining} drawn, {batch.remaining} remaining.
              </p>
            )}
          </div>
          <ParentTags parents={values.parents} onChange={(parents) => set({ parents })} exclude={tagId ?? undefined} />
          <Field label="Tag of the new piece" htmlFor="sf-new-tag"
            hint="Scan or paste the id on the new tag. Empty: a new id is generated.">
            <TagField id="sf-new-tag" value={values.tag} onChange={(tag) => set({ tag })} />
          </Field>
          {tagId && tagFree && (
            <p className={`text-xs ${tagFree.ok ? 'text-green-700 dark:text-green-400' : 'text-destructive'}`}>{tagFree.message}</p>
          )}
        </section>
      )}

      {step === 'details' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Details</h2>
            {(mode === 'new' || mode === 'cut') && tagId && props.tag && (
              <p className="break-all text-xs text-muted-foreground">
                Tag <span className="font-mono">{tagId}</span>
                {tagFree && <span className={tagFree.ok ? ' text-green-700 dark:text-green-400' : ' text-destructive'}>
                  {' '}- {tagFree.message}</span>}
              </p>
            )}
            {mode === 'state' && (
              <p className="text-sm text-muted-foreground">
                A new state is for a changed shape (cut down, repaired). Damage or weathering without a change of
                shape is evidence: Add evidence, visual inspection.
              </p>
            )}
            {mode === 'correct' && (
              <p className="text-sm text-muted-foreground">
                A correction replaces this version and keeps its date. Name, notes, location and colour can also
                be edited in place.
              </p>
            )}
          </div>
          <DetailsStep mode={mode} values={values}
            set={(patch) => {
              if ('dataset' in patch) datasetTouched.current = true
              set(patch)
            }}
            setFields={setFields} datasets={datasets} materials={materials} batch={batch} />
        </section>
      )}

      {step === 'size' && (
        <section className="space-y-4 border-t border-border pt-6">
          <h2 className="text-lg font-semibold">Size</h2>
          <SizeStep mode={mode} values={values} set={set} column={column} currentSize={currentSize}
            batch={batch !== null} />
        </section>
      )}

      {step === 'photos' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Photos</h2>
            <p className="text-sm text-muted-foreground">
              A general impression of the piece. Use the camera on site or pick images from the device; they
              upload when you submit. Private persons, faces and number plates must not be on them.
            </p>
          </div>
          <SnapshotPhotoCapture mode="staged" files={values.photos} onFilesChange={(photos) => set({ photos })} />
        </section>
      )}

      {step === 'inspection' && (
        <section className="space-y-4 border-t border-border pt-6">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">Visual inspection (optional)</h2>
            <p className="text-sm text-muted-foreground">
              An overall condition grade with its findings and photos is evidence, recorded in the evidence form
              once the component exists.
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4" checked={values.inspect}
              onChange={(event) => set({ inspect: event.target.checked })} />
            Record a visual inspection next
          </label>
        </section>
      )}

      {step === 'review' && (
        <section className="space-y-4 border-t border-border pt-6">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            Review and submit
          </h2>
          <dl className="grid gap-2 text-sm">
            {tagId && <Row label="Tag" value={<span className="break-all font-mono text-xs">{tagId}</span>} />}
            {mode === 'cut' && <Row label="Parents" value={`${values.parents.length}`} />}
            {(mode === 'new' || mode === 'cut') && (
              <Row label="Dataset" value={datasets.find((d) => d._id === values.dataset)?.name ?? values.dataset} />
            )}
            {mode === 'new' && (
              <Row label="Function / material"
                value={`${values.originalFunction ? ORIGINAL_FUNCTION_LABELS[values.originalFunction] : ''} / ${materials.find((m) => m._id === values.material)?.label ?? values.material}`} />
            )}
            <Row label="Name" value={values.fields.name.trim() || (mode === 'new' || mode === 'cut' ? 'The catalog number' : 'Unchanged')} />
            <Row label="Size X x Y x Z (mm)" value={batch && !values.sizeEntered ? "The batch's proxy"
              : values.sizeEntered || mode !== 'correct' ? (boxText ?? 'Missing') : 'Geometry kept'} />
            <Row label={batch ? 'Pieces drawn' : 'Quantity'} value={String(values.fields.quantity)} />
            <Row label="Colour" value={<span className="inline-flex items-center gap-2">
              <span className="inline-block h-3 w-3 rounded-full border border-border" style={{ background: `rgb(${rgb.join(',')})` }} />
              {rgb.join('/')}</span>} />
            <Row label="Photos" value={String(values.photos.length)} />
            {mode === 'new' && <Row label="Visual inspection next" value={values.inspect ? 'Yes' : 'No'} />}
          </dl>

          {mode === 'correct' && values.sizeEntered && identity && positioned && (
            <PositionedEvidence identityId={identity._id} records={positioned} newTab />
          )}

          <p className="text-xs text-muted-foreground">
            {'You submit it for review; a moderator of the dataset publishes it' +
              (moderator ? ' (you may publish your own from the Moderation queue)' : '') +
              (mode === 'cut'
                ? batch
                  ? (drawsRest
                    ? '. Publishing the rest of the batch takes it out of circulation as split'
                    : '. The batch stays in circulation while pieces remain')
                  : '. Publishing it ends the parents' + "'" + ' circulation'
                : '') + '.'}
          </p>

          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          {progress.current && (
            <p className="text-xs text-muted-foreground">
              The draft exists already; submitting again continues from where it stopped
              {' '}(<Link href={`/components/${progress.current.identityId}`} className="underline underline-offset-4">open it</Link>).
            </p>
          )}
        </section>
      )}

      {error && step !== 'review' && <p role="alert" className="text-sm text-destructive">{error}</p>}

      <div className="flex justify-between gap-2 border-t border-border pt-4">
        <Button type="button" variant="outline" onClick={back} disabled={index === 0 || busy}>
          <ArrowLeft className="mr-2 h-4 w-4" />Back
        </Button>
        {step !== 'review' ? (
          <div className="flex flex-col items-end gap-1">
            <Button type="button" onClick={next} disabled={blocking.length > 0 || (scanned && step === 'details')}>
              Continue<ArrowRight className="ml-2 h-4 w-4" />
            </Button>
            {blocking[0] && <p className="max-w-xs text-right text-xs text-muted-foreground">{blocking[0].message}</p>}
          </div>
        ) : (
          <Button type="button" onClick={() => void submit()} disabled={busy || scanned}>
            {busy ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Submitting...</> : <><PackagePlus className="mr-2 h-4 w-4" />{mode === 'new' ? 'Create component' : mode === 'cut' ? (batch ? 'Draw pieces' : 'Record piece') : mode === 'state' ? 'Record state' : 'Record correction'}</>}
          </Button>
        )}
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b border-border/60 py-1.5">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="text-right">{value}</dd>
    </div>
  )
}
