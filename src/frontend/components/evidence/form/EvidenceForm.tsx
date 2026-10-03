'use client'

/**
 * The evidence form (spec 7.6, decision 7.1): one form from the component
 * page, on a phone right after a tag scan or on a desktop. The method
 * picker drives a sub-form generated from the registry; fan-out, repeat
 * from my last record and apply-to-several-pieces all end in one
 * `POST /evidence/bulk`. The records are saved as drafts first: the review
 * step shows what the server computed and warned about, and only then are
 * they submitted (and, for a moderator, published).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, History, Loader2, Save } from 'lucide-react'
import { toast } from 'sonner'

import { Field } from '@/components/evidence/controls'
import EvidenceCard from '@/components/evidence/EvidenceCard'
import ActorsField from '@/components/evidence/form/ActorsField'
import { PiecesField, SummaryEditor } from '@/components/evidence/form/ClaimEditor'
import FilesField from '@/components/evidence/form/FilesField'
import InspectionEditor from '@/components/evidence/form/InspectionEditor'
import PositionField from '@/components/evidence/form/PositionField'
import RecordsEditor, { gridOf, gridToForm } from '@/components/evidence/form/RecordsEditor'
import {
  buildItems,
  initialState,
  newRecord,
  pairingCandidates,
  repeatedRecord,
  stateFromLast,
  stateFromRecord,
  type BuildContext,
  type FormState,
  type RecordState,
} from '@/components/evidence/form/state'
import PositionPickerDialog, { type PickerResult } from '@/components/evidence/PositionPickerDialog'
import SchemaFields from '@/components/evidence/SchemaFields'
import type { ViewerMark } from '@/components/viewer/EvidenceMarks'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { EvidenceView } from '@/generated'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { EVIDENCE_METHOD_LABELS, SOURCE_TIER_LABELS, vocabLabel } from '@/generated/Vocab'
import { BackendError, backendJson } from '@/lib/backend'
import {
  UPLOAD_HELP,
  createBulk,
  evidenceAction,
  deleteEvidence,
  loadEvidenceOf,
  myLatestRecord,
  problemsOf,
  uploadAttachment,
  type JsonSchema,
  type MethodInfo,
  type ProblemRow,
} from '@/lib/evidence/api'
import { gridPoints } from '@/lib/evidence/grid'
import { layoutOf } from '@/lib/evidence/layout'
import { prepareUpload } from '@/lib/evidence/photos'
import { getAt, isBlank, parseNumber, setAt } from '@/lib/evidence/schema'
import { useRegistry } from '@/lib/evidence/useRegistry'
import { useMe } from '@/lib/me'
import { isMe } from '@/components/evidence/form/ActorsField'

type Picker =
  | { mode: 'point'; recordKey: string }
  | { mode: 'grid'; recordKey: string }
  | { mode: 'locations' }

const NO_PROBLEMS: ProblemRow[] = []

function actorRootOf(methods: MethodInfo[]): JsonSchema | null {
  return methods.find((m) => m.payload_schema.$defs?.Actor)?.payload_schema ?? null
}

export default function EvidenceForm({
  identityId,
  correctId,
}: {
  identityId: string
  correctId?: string
}) {
  const router = useRouter()
  const { me, moderates, rolesIn, loading: meLoading } = useMe()
  const { registry, error: registryError } = useRegistry()

  const [catalog, setCatalog] = useState<CatalogComponent | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [groupOf, setGroupOf] = useState<string | null>(null)
  const [corrected, setCorrected] = useState<EvidenceView | null>(null)
  const [rebounds, setRebounds] = useState<EvidenceView[]>([])
  const [cores, setCores] = useState<EvidenceView[]>([])

  const [state, setState] = useState<FormState | null>(null)
  const [problems, setProblems] = useState<ProblemRow[]>([])
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState<EvidenceView[] | null>(null)
  const [uploadNotes, setUploadNotes] = useState<string[]>([])
  const [picker, setPicker] = useState<Picker | null>(null)
  const [loadingLast, setLoadingLast] = useState(false)
  const topRef = useRef<HTMLDivElement>(null)

  // THE PIECE ----------------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    Promise.all([
      backendJson<CatalogComponent>(`/identities/${encodeURIComponent(identityId)}/compose`),
      backendJson<{ _id: string; group: string }[]>('/materials').catch(() => []),
      loadEvidenceOf(identityId, 'method=rebound_hammer&status=all').catch(() => []),
      loadEvidenceOf(identityId, 'method=core_compression&status=all').catch(() => []),
      correctId ? backendJson<EvidenceView>(`/evidence/${encodeURIComponent(correctId)}`) : Promise.resolve(null),
    ])
      .then(([passport, materials, reb, core, record]) => {
        if (cancelled) return
        setCatalog(passport)
        const material = materials.find((m) => m._id === passport.identity.material)
        setGroupOf(material?.group ?? null)
        setRebounds(reb)
        setCores(core)
        setCorrected(record)
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : 'Could not load the component')
      })
    return () => { cancelled = true }
  }, [identityId, correctId])

  const method = registry?.methods.find((m) => m.name === state?.method) ?? null
  const layout = method ? layoutOf(method.name) : null
  const actorRoot = useMemo(() => (registry ? actorRootOf(registry.methods) : null), [registry])
  const snapshot = catalog ? primarySnapshot(catalog) : null
  const snapshotId = snapshot ? String(snapshot._id ?? '') : ''
  const dataset = catalog?.identity.dataset ?? null
  const canContribute = rolesIn(dataset).includes('contributor')
  const isModerator = moderates(dataset)

  // a correction opens with the record's values
  useEffect(() => {
    if (!corrected || !registry || state) return
    const m = registry.methods.find((x) => x.name === corrected.method)
    if (m) setState(stateFromRecord(m, corrected, actorRoot))
  }, [corrected, registry, state, actorRoot])

  const pick = (name: string) => {
    if (!registry) return
    const m = registry.methods.find((x) => x.name === name)
    if (m) {
      setState(initialState(m, identityId))
      setProblems([])
      setCreated(null)
    }
  }

  const patch = useCallback((next: Partial<FormState>) => {
    setState((prev) => (prev ? { ...prev, ...next } : prev))
  }, [])

  const loadLast = async () => {
    if (!method || !me || !dataset) return
    setLoadingLast(true)
    try {
      const last = await myLatestRecord(method.name, dataset)
      if (!last) {
        toast.info('You have no earlier record of this method in this dataset.')
        return
      }
      setState(stateFromLast(method, identityId, last, actorRoot))
      toast.success('Instrument, performers and standard filled in from your last record')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not load your last record')
    } finally {
      setLoadingLast(false)
    }
  }

  // PROBLEMS BY RECORD --------------------------------------------------------
  const recordProblems = useCallback(
    (index: number) => {
      const rows = problems.filter((p) => (p.record ?? 0) === index)
      return rows.length ? rows : NO_PROBLEMS
    },
    [problems],
  )
  const envelopeProblems = (prefix: string) =>
    problems.filter((p) => p.path.startsWith(prefix)).map((p) => p.message)

  // THE PICKER ----------------------------------------------------------------
  const marksOfForm = useMemo<ViewerMark[]>(() => {
    if (!state) return []
    return state.records.flatMap((record, index): ViewerMark[] => {
      const grid = gridOf(record.payload)
      if (grid && record.position.snapshotId) {
        return [{
          id: `form-${record.key}`, snapshotId: record.position.snapshotId, kind: 'grid',
          points: gridPoints(grid), color: '#64748b', grid: { rows: grid.rows, cols: grid.cols },
          label: String(index + 1),
        }]
      }
      if (record.position.kind === 'point' && record.position.point && record.position.snapshotId) {
        return [{
          id: `form-${record.key}`, snapshotId: record.position.snapshotId, kind: 'point',
          points: [record.position.point], color: '#64748b', label: String(index + 1),
        }]
      }
      return []
    })
  }, [state])

  const pickerRecord = state && picker && 'recordKey' in picker
    ? state.records.find((r) => r.key === picker.recordKey) ?? null
    : null

  const onPickerConfirm = (result: PickerResult) => {
    if (!state || !method || !picker) return
    if (result.kind === 'point' && pickerRecord) {
      patch({
        records: state.records.map((r) => (r.key === pickerRecord.key
          ? { ...r, position: { ...r.position, kind: 'point', snapshotId: result.snapshotId, point: result.point } }
          : r)),
      })
    } else if (result.kind === 'grid' && picker.mode === 'grid' && pickerRecord) {
      patch({
        records: state.records.map((r) => (r.key === pickerRecord.key
          ? {
            ...r,
            payload: setAt(r.payload, ['test_area', 'grid'], gridToForm(result.grid)),
            position: { ...r.position, kind: 'region', snapshotId: result.snapshotId, point: null },
          }
          : r)),
      })
      if (result.tooClose.length) {
        toast.warning(`${result.tooClose.length} grid points are closer to an edge than allowed.`)
      }
    } else if (result.kind === 'grid' && picker.mode === 'locations') {
      const template = state.records[state.records.length - 1]
      const labelPath = method.name === 'core_compression' ? ['specimen', 'label'] : ['test_area', 'label']
      const make = (point: [number, number, number], index: number): RecordState => {
        const base = template ? repeatedRecord(method, template) : newRecord(method)
        return {
          ...base,
          payload: setAt(base.payload, labelPath, `L${index + 1}`),
          position: { kind: 'point', description: '', snapshotId: result.snapshotId, point },
        }
      }
      const points = gridPointsOf(result)
      const fresh = points.map(make)
      const pristine = state.records.every((r) => isBlank(r.payload.readings) && isBlank(getAt(r.payload, ['specimen', 'measured_diameter_mm']))
        && r.position.kind === 'none' && !r.position.description)
      patch({ records: pristine ? fresh : [...state.records, ...fresh] })
      toast.success(`${fresh.length} test locations added`)
    }
  }

  // SAVING ----------------------------------------------------------------------
  const context: BuildContext | null = method && registry && snapshotId
    ? { identityId, method, actorRoot, snapshotId, quantities: registry.quantities }
    : null

  const save = async () => {
    if (!state || !method || !context || !layout) return
    setSaving(true)
    setProblems([])
    try {
      const items = buildItems(state, context)
      if (items.length === 0) {
        setProblems([{ path: '', message: 'Add at least one record.' }])
        return
      }
      let records: EvidenceView[]
      if (corrected) {
        const { identity_id: _unused, ...body } = items[0] as unknown as Record<string, unknown>
        void _unused
        records = [await backendJson<EvidenceView>(`/evidence/${encodeURIComponent(corrected._id)}/supersede`, {
          method: 'POST', body,
        })]
      } else {
        records = await createBulk(items, false)
      }
      const notes = await attachFiles(state, records, layout.fanOut)
      setUploadNotes(notes)
      // the files are on the records now: show the records as they are stored
      const stored = await Promise.all(records.map((r) =>
        backendJson<EvidenceView>(`/evidence/${encodeURIComponent(r._id)}`).catch(() => r)))
      setCreated(stored)
      topRef.current?.scrollIntoView({ behavior: 'smooth' })
    } catch (err) {
      const rows = problemsOf(err)
      if (rows.length) {
        setProblems(rows)
        toast.error('Some values need another look.')
      } else {
        const text = err instanceof BackendError ? err.message : 'Could not save the records'
        setProblems([{ path: '', message: text }])
        toast.error(text)
      }
    } finally {
      setSaving(false)
    }
  }

  const reload = useCallback(async () => {
    if (!created) return
    const fresh = await Promise.all(created.map((r) =>
      backendJson<EvidenceView>(`/evidence/${encodeURIComponent(r._id)}`).catch(() => r)))
    setCreated(fresh)
  }, [created])

  const submitAll = async (publish: boolean) => {
    if (!created) return
    setSaving(true)
    try {
      for (const record of created.filter((r) => r.status === 'draft')) {
        await evidenceAction(record._id, 'submit', undefined, publish ? '?publish=1' : '')
      }
      toast.success(publish ? 'Submitted and published' : 'Submitted for moderation')
      await reload()
      router.refresh()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Submit failed')
      await reload()
    } finally {
      setSaving(false)
    }
  }

  const editAgain = async () => {
    if (!created) return
    if (!window.confirm('Go back to the form? These drafts are deleted and the form keeps what you entered.')) return
    setSaving(true)
    try {
      for (const record of created.filter((r) => r.status === 'draft')) await deleteEvidence(record._id)
      setCreated(null)
      setUploadNotes([])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not delete the drafts')
    } finally {
      setSaving(false)
    }
  }

  // RENDER ----------------------------------------------------------------------
  const back = (
    <Link href={`/components/${encodeURIComponent(identityId)}`}
      className="inline-flex items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:underline">
      <ArrowLeft className="h-4 w-4" />Back to the component
    </Link>
  )

  if (loadError || registryError) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 p-4">
        {back}
        <p className="text-sm text-destructive" role="alert">{loadError ?? registryError}</p>
      </div>
    )
  }
  if (!catalog || !registry || meLoading) {
    return (
      <div className="mx-auto flex max-w-3xl items-center gap-2 p-6 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />Loading...
      </div>
    )
  }
  const identity = catalog.identity
  const title = `#${identity.catalog_number} ${snapshot?.name ?? ''}`.trim()

  if (!canContribute) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 p-4">
        {back}
        <h1 className="text-xl font-bold">Add evidence</h1>
        <p className="text-sm" role="status">
          Recording evidence about {title} needs the contributor role in its dataset
          {me ? '. Ask a moderator of the dataset to add it.' : '. Sign in first.'}
        </p>
      </div>
    )
  }

  if (created) {
    const drafts = created.filter((r) => r.status === 'draft')
    return (
      <div ref={topRef} className="mx-auto max-w-3xl space-y-4 p-4 pb-24">
        {back}
        <h1 className="text-xl font-bold">{corrected ? 'Check the correction' : 'Check the records'}</h1>
        <p className="text-sm text-muted-foreground">
          {drafts.length > 0
            ? 'Saved as drafts. Check what the server computed and any warnings, then submit. Nothing reaches the catalog before a moderator publishes it.'
            : 'Saved.'}
        </p>
        {uploadNotes.length > 0 && (
          <ul className="space-y-1 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100" role="alert">
            {uploadNotes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        )}
        <div className="space-y-2">
          {created.map((record) => (
            <EvidenceCard key={record._id} record={record} dataset={dataset} defaultOpen
              onChanged={() => void reload()} uploadHelp={registry.help(...UPLOAD_HELP)} />
          ))}
        </div>
        <div className="sticky bottom-0 -mx-4 flex flex-wrap gap-2 border-t border-border bg-background/95 p-3 backdrop-blur">
          {drafts.length > 0 && (
            <>
              <Button disabled={saving} onClick={() => void submitAll(false)}>
                Submit {drafts.length > 1 ? `all ${drafts.length}` : ''}
              </Button>
              {isModerator && (
                <Button variant="outline" disabled={saving} onClick={() => void submitAll(true)}>
                  Submit and publish
                </Button>
              )}
              {!corrected && (
                <Button variant="ghost" disabled={saving} onClick={() => void editAgain()}>
                  Back to the form
                </Button>
              )}
            </>
          )}
          <Button asChild variant={drafts.length ? 'ghost' : 'default'}>
            <Link href={`/components/${encodeURIComponent(identityId)}`}>Done</Link>
          </Button>
        </div>
      </div>
    )
  }

  const methods = registry.methods
  const help = registry.help
  const hasMeActor = !!state && state.performers.some((a) => isMe(a, me))
  const date = state && method && method.context_time !== 'sampled_at'

  return (
    <div ref={topRef} className="mx-auto max-w-3xl space-y-4 p-4 pb-28">
      {back}
      <div>
        <h1 className="text-xl font-bold">{corrected ? 'Correct a record' : 'Add evidence'}</h1>
        <p className="text-sm text-muted-foreground">{title}{dataset ? ` (${dataset})` : ''}</p>
        {corrected && (
          <p className="mt-1 text-xs text-muted-foreground">
            The corrected record stays; the new one replaces it in the lists and the fold once a moderator publishes it.
          </p>
        )}
      </div>

      {!corrected && (
        <section aria-label="Method" className="space-y-2">
          <h2 className="text-sm font-semibold">What kind of evidence</h2>
          <div role="radiogroup" aria-label="Evidence method" className="grid gap-2 sm:grid-cols-2">
            {methods.map((m) => {
              const active = state?.method === m.name
              return (
                <button
                  key={m.name}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  onClick={() => pick(m.name)}
                  className={`rounded-lg border p-3 text-left text-sm transition-colors ${
                    active ? 'border-primary bg-primary/5 ring-1 ring-primary/30' : 'border-border hover:bg-muted/40'
                  }`}
                >
                  <span className="block font-medium">{vocabLabel(EVIDENCE_METHOD_LABELS, m.name)}</span>
                  <span className="block text-xs text-muted-foreground">
                    {m.tier_from_payload ? 'Source depends on the basis' : vocabLabel(SOURCE_TIER_LABELS, m.source_tier)}
                  </span>
                  {describes(m) && (
                    <span className="mt-1 line-clamp-2 block text-xs text-muted-foreground">{firstSentence(describes(m))}</span>
                  )}
                </button>
              )
            })}
          </div>
        </section>
      )}

      {state && method && layout && (
        <>
          {describes(method) && <p className="text-sm text-muted-foreground">{describes(method)}</p>}

          <section aria-label="Who and when" className="space-y-3 rounded-lg border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Who and when</h2>
              {!corrected && (
                <Button type="button" variant="outline" size="sm" className="h-8 text-xs" disabled={loadingLast}
                  onClick={() => void loadLast()}>
                  {loadingLast ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <History className="mr-1 h-3.5 w-3.5" />}
                  Repeat from my last record
                </Button>
              )}
            </div>
            {actorRoot && (
              <ActorsField
                actors={state.performers}
                onChange={(performers) => patch({ performers })}
                root={actorRoot}
                me={me}
                idPrefix="performer"
              />
            )}
            {date && (
              <Field id="observed-at" label="Date of the observation" help={help('EvidenceCreate', 'observed_at')} required
                errors={envelopeProblems('observed_at')}>
                <Input id="observed-at" type="date" value={state.observedAt}
                  onChange={(e) => patch({ observedAt: e.target.value })} className="max-w-48" />
              </Field>
            )}
            <div className="grid grid-cols-[1fr_6rem] gap-2">
              <Field id="standard-code" label="Standard"
                help={method.default_standard ? `Defaults to ${method.default_standard.code}${method.default_standard.year ? ` (${method.default_standard.year})` : ''}` : ''}
                errors={envelopeProblems('standard')}>
                <Input id="standard-code" value={state.standardCode}
                  placeholder={method.default_standard?.code ?? 'e.g. EN 12504-2'}
                  onChange={(e) => patch({ standardCode: e.target.value })} />
              </Field>
              <Field id="standard-year" label="Year">
                <Input id="standard-year" inputMode="numeric" value={state.standardYear}
                  placeholder={method.default_standard?.year ? String(method.default_standard.year) : ''}
                  onChange={(e) => patch({ standardYear: e.target.value })} />
              </Field>
            </div>
            {hasMeActor && (
              <div className="flex items-start gap-2">
                <Checkbox id="self-attested" checked={state.selfAttested}
                  onCheckedChange={(c) => patch({ selfAttested: c === true })} className="mt-0.5" />
                <Label htmlFor="self-attested" className="text-sm font-normal">
                  I performed this and stand by the result
                </Label>
              </div>
            )}
          </section>

          {layout.fanOut === 'areas' && (
            <RecordsEditor
              idPrefix="record"
              method={method}
              quantities={registry.quantities}
              records={state.records}
              shared={state.shared}
              onRecords={(records) => patch({ records })}
              onShared={(shared) => patch({ shared })}
              problems={recordProblems}
              rebounds={pairingCandidates(rebounds, cores, '', [])}
              help={help}
              onPickPoint={(recordKey) => setPicker({ mode: 'point', recordKey })}
              onPickGrid={(recordKey) => setPicker({ mode: 'grid', recordKey })}
              onAddLocations={() => setPicker({ mode: 'locations' })}
            />
          )}

          {layout.fanOut === 'observations' && (
            <InspectionEditor
              idPrefix="finding"
              method={method}
              quantities={registry.quantities}
              materialGroup={groupOf}
              observations={state.observations}
              photos={state.photos}
              onObservations={(observations) => patch({ observations })}
              onPhotos={(photos) => patch({ photos })}
              errors={(index) => problems.filter((p) => (p.record ?? 0) === index).map((p) => p.message)}
            />
          )}

          {(layout.fanOut === 'pieces' || layout.fanOut === 'single') && state.records[0] && (
            <section className="space-y-3">
              <fieldset className="space-y-3 rounded-md border border-border/70 p-3">
                <legend className="px-1 text-sm font-semibold">{vocabLabel(EVIDENCE_METHOD_LABELS, method.name)}</legend>
                <SchemaFields
                  schema={method.payload_schema}
                  root={method.payload_schema}
                  value={state.records[0].payload}
                  onChange={(payload) => patch({ records: [{ ...state.records[0], payload }] })}
                  idPrefix="claim"
                  layout={layout}
                  errors={Object.fromEntries(problems
                    .filter((p) => p.path.startsWith('payload.'))
                    .map((p) => [p.path.slice(8), [p.message]]))}
                />
              </fieldset>
              {layout.fanOut === 'pieces' && (
                <>
                  <SummaryEditor
                    id="summary"
                    method={method}
                    quantities={registry.quantities}
                    value={state.summary}
                    onChange={(summary) => patch({ summary })}
                    errors={envelopeProblems('summary')}
                    helpFor={(field) => help('SummaryInput', field)}
                  />
                  {!corrected && (
                    <PiecesField pieces={state.pieces} onChange={(pieces) => patch({ pieces })} thisPiece={identityId} />
                  )}
                </>
              )}
              {layout.fanOut === 'single' && (
                <PositionField
                  id="layout-position"
                  position={state.records[0].position}
                  onChange={(position) => patch({ records: [{ ...state.records[0], position }] })}
                  onPick={() => undefined}
                  noPoint
                  errors={envelopeProblems('position')}
                  help={help('PositionInput', 'description')}
                />
              )}
              {layout.fanOut === 'single' && (
                <p className="text-xs text-muted-foreground">
                  The bars are in the stored coordinates of the version you see on the component page.
                </p>
              )}
            </section>
          )}

          {!corrected && (
            <section aria-label="Files" className="space-y-2 rounded-lg border border-border p-3">
              <FilesField
                files={state.files}
                onChange={(files) => patch({ files })}
                help={help(...UPLOAD_HELP)}
                label={layout.fanOut === 'observations' ? 'Other files (a report, a drawing)' : 'Files for all records'}
              />
            </section>
          )}

          <section aria-label="Notes" className="space-y-1">
            <Label htmlFor="notes" className="text-xs">Notes</Label>
            <Textarea id="notes" rows={2} value={state.notes} onChange={(e) => patch({ notes: e.target.value })} />
          </section>

          {problems.filter((p) => !p.path.startsWith('payload') && !p.path.startsWith('position')
            && !p.path.startsWith('derived') && !p.path.startsWith('summary')
            && !p.path.startsWith('standard') && !p.path.startsWith('observed_at')).length > 0 && (
            <ul className="space-y-1 rounded-md border border-red-300 bg-red-50 p-2 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/40 dark:text-red-100" role="alert">
              {problems.filter((p) => !p.path.startsWith('payload') && !p.path.startsWith('position')
                && !p.path.startsWith('derived') && !p.path.startsWith('summary')
                && !p.path.startsWith('standard') && !p.path.startsWith('observed_at')).map((p, i) => (
                <li key={i}>{p.record !== undefined && state.records.length + state.observations.length > 1 ? `Record ${p.record + 1}: ` : ''}{p.path ? `${p.path}: ` : ''}{p.message}</li>
              ))}
            </ul>
          )}

          <div className="sticky bottom-0 -mx-4 flex flex-wrap items-center gap-2 border-t border-border bg-background/95 p-3 backdrop-blur">
            <Button onClick={() => void save()} disabled={saving}>
              {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
              {corrected ? 'Save the correction and check' : 'Save as drafts and check'}
            </Button>
            <p className="text-xs text-muted-foreground">
              {layout.fanOut === 'areas' ? `${state.records.length} record${state.records.length === 1 ? '' : 's'}`
                : layout.fanOut === 'observations' ? `${state.observations.length} record${state.observations.length === 1 ? '' : 's'}`
                  : layout.fanOut === 'pieces' ? `${state.pieces.length} record${state.pieces.length === 1 ? '' : 's'}` : ''}
              {problems.length > 0 && ', see the marked fields'}
            </p>
          </div>

          {picker && (
            <PositionPickerDialog
              open
              onOpenChange={(open) => { if (!open) setPicker(null) }}
              catalog={catalog}
              mode={picker.mode === 'point' ? 'point' : 'grid'}
              initialGrid={pickerRecord ? gridOf(pickerRecord.payload) : null}
              minSpacingMm={picker.mode === 'locations' ? 1
                : parseNumber(String(getAt(pickerRecord?.payload ?? {}, ['test_area', 'min_spacing_mm']) ?? '')) ?? 25}
              minEdgeMm={method.name === 'rebound_hammer'
                ? parseNumber(String(getAt(pickerRecord?.payload ?? state.records[0]?.payload ?? {}, ['test_area', 'min_edge_distance_mm']) ?? '')) ?? 25
                : undefined}
              defaults={pickerRecord ? gridDefaults(pickerRecord) : { rows: 2, cols: 2, spacing: 100 }}
              context={marksOfForm.filter((m) => m.points.length > 0)}
              onConfirm={onPickerConfirm}
            />
          )}
        </>
      )}
    </div>
  )
}

/** The method's description, or nothing when it only repeats its name. */
function describes(method: MethodInfo): string {
  const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase()
  const text = method.description ?? ''
  return !text.trim() || same(text, method.label) || same(text, vocabLabel(EVIDENCE_METHOD_LABELS, method.name))
    ? ''
    : text
}

function firstSentence(text: string): string {
  const end = text.search(/\.\s/)
  return end > 0 ? text.slice(0, end + 1) : text
}

function gridPointsOf(result: Extract<PickerResult, { kind: 'grid' }>): [number, number, number][] {
  const { grid } = result
  const points: [number, number, number][] = []
  for (let r = 0; r < grid.rows; r += 1) {
    for (let c = 0; c < grid.cols; c += 1) {
      points.push([
        grid.origin[0] + grid.u[0] * c * grid.spacing_mm + grid.v[0] * r * grid.spacing_mm,
        grid.origin[1] + grid.u[1] * c * grid.spacing_mm + grid.v[1] * r * grid.spacing_mm,
        grid.origin[2] + grid.u[2] * c * grid.spacing_mm + grid.v[2] * r * grid.spacing_mm,
      ])
    }
  }
  return points
}

/** Rows and columns that match the readings entered so far (3 x 3 for nine). */
function gridDefaults(record: RecordState): { rows?: number; cols?: number; spacing?: number } {
  const readings = Array.isArray(record.payload.readings) ? record.payload.readings.length : 0
  for (const rows of [3, 2, 4, 5, 6, 1]) {
    if (readings >= rows && readings % rows === 0 && readings / rows >= 1 && readings / rows <= 100) {
      return { rows, cols: readings / rows }
    }
  }
  return {}
}

async function attachFiles(
  state: FormState,
  records: EvidenceView[],
  fanOut: string,
): Promise<string[]> {
  const notes: string[] = []
  const ids = records.map((r) => r._id)
  const send = async (file: File, to: string[]) => {
    try {
      await uploadAttachment(await prepareUpload(file), to)
    } catch (err) {
      notes.push(`${file.name} was not attached: ${err instanceof Error ? err.message : 'upload failed'}. Add it to the record below.`)
    }
  }
  for (const file of state.files) await send(file, ids)
  if (fanOut === 'observations') {
    for (const photo of state.photos) {
      const to = state.observations
        .map((o, i) => (o.photoIds.includes(photo.id) ? ids[i] : null))
        .filter((id): id is string => !!id)
      if (to.length) await send(photo.file, to)
    }
  }
  return notes
}
