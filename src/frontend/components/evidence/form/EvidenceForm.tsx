'use client'

/**
 * The evidence form (spec 7.6, decisions 7.1, 8.134): one form from the
 * component page, on a phone right after a tag scan or on a desktop, in
 * numbered sections (method, who and when, what was found, files, notes,
 * check and save) with an outline beside it (a progress line on a phone) and
 * a state per section. The method picker drives a sub-form generated from the
 * registry; fan-out, repeat from my last record and apply-to-several-pieces
 * all end in one `POST /evidence/bulk`. The records are saved as drafts
 * first: the review step shows what the server computed and warned about, and
 * only then are they submitted. Nobody publishes directly (8.120): a
 * moderator of the dataset publishes from the queue, also their own records.
 * `editId` opens a draft (a pending record for a moderator) with its values
 * and saves with `PATCH /evidence/{id}`: the status and the attachments stay
 * (8.127). Create, edit and correct share the layout; the heading names the
 * mode, the piece and the version.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { ArrowLeft, FileText, History, Loader2, Save, Undo2 } from 'lucide-react'
import { toast } from 'sonner'

import { useConfirm } from '@/components/common/ConfirmDialog'
import { Field } from '@/components/evidence/controls'
import EvidenceCard from '@/components/evidence/EvidenceCard'
import ActorsField, { isMe, meActor } from '@/components/evidence/form/ActorsField'
import BarsEditor from '@/components/evidence/form/BarsEditor'
import CheckSection from '@/components/evidence/form/CheckSection'
import { PiecesField, SummaryEditor } from '@/components/evidence/form/ClaimEditor'
import FilesField from '@/components/evidence/form/FilesField'
import {
  FormSection,
  Outline,
  ProgressLine,
  jumpToSection,
  useActiveStep,
  type FormStepId,
  type Step,
} from '@/components/evidence/form/FormShell'
import InspectionEditor from '@/components/evidence/form/InspectionEditor'
import MethodPicker from '@/components/evidence/form/MethodPicker'
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
import { DateField } from '@/components/ui/date-field'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { EvidenceView } from '@/generated'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { primarySnapshot } from '@/generated/catalogExtras'
import { EVIDENCE_METHOD_LABELS, vocabLabel } from '@/generated/Vocab'
import { BackendError, backendJson } from '@/lib/backend'
import { formatDay } from '@/lib/componentDetail'
import { orderMethods } from '@/lib/evidence/order'
import {
  UPLOAD_HELP,
  createBulk,
  evidenceAction,
  actorRootOf,
  deleteEvidence,
  loadAttachments,
  loadEvidenceOf,
  myLatestRecord,
  patchEvidence,
  problemsOf,
  removeAttachment,
  uploadAttachment,
  type AttachmentEntry,
  type MethodInfo,
  type ProblemRow,
} from '@/lib/evidence/api'
import { canEditEvidence, editBody, verificationNotices } from '@/lib/evidence/edit'
import { gridPoints } from '@/lib/evidence/grid'
import {
  SECTION_ORDER,
  formIssues,
  issuesOf,
  sectionStates,
  serverIssues,
  type Issue,
  type SectionId,
} from '@/lib/evidence/issues'
import { layoutOf } from '@/lib/evidence/layout'
import { prepareUpload } from '@/lib/evidence/photos'
import { getAt, isBlank, parseNumber, setAt, type FormObject } from '@/lib/evidence/schema'
import { useRegistry } from '@/lib/evidence/useRegistry'
import { useMe } from '@/lib/me'

type Picker =
  | { mode: 'point'; recordKey: string }
  | { mode: 'grid'; recordKey: string }
  | { mode: 'locations' }

const NO_PROBLEMS: ProblemRow[] = []

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

export default function EvidenceForm({
  identityId,
  correctId,
  editId,
  initialMethod,
}: {
  identityId: string
  correctId?: string
  /** Opens the record of this id to change it (a draft, a pending one for a moderator). */
  editId?: string
  /** Opens with this method picked (the snapshot form's inspection step, 7.9). */
  initialMethod?: string
}) {
  const router = useRouter()
  const { me, rolesIn, moderates, loading: meLoading } = useMe()
  const { registry, error: registryError } = useRegistry()
  const { confirm, dialog } = useConfirm()

  const [catalog, setCatalog] = useState<CatalogComponent | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [groupOf, setGroupOf] = useState<string | null>(null)
  // the record the form starts from: the one being corrected or the one being edited
  const [corrected, setCorrected] = useState<EvidenceView | null>(null)
  const [rebounds, setRebounds] = useState<EvidenceView[]>([])
  const [cores, setCores] = useState<EvidenceView[]>([])
  // the files of the record a correction replaces: they come over unless dropped (RL4)
  const [carried, setCarried] = useState<AttachmentEntry[]>([])
  const [dropped, setDropped] = useState<Set<number>>(() => new Set())

  const [state, setState] = useState<FormState | null>(null)
  const sourceId = editId ?? correctId
  const editing = Boolean(editId)
  const [problems, setProblems] = useState<ProblemRow[]>([])
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState<EvidenceView[] | null>(null)
  const [uploadNotes, setUploadNotes] = useState<string[]>([])
  const [picker, setPicker] = useState<Picker | null>(null)
  const [loadingLast, setLoadingLast] = useState(false)
  // my latest record of any method in this dataset, for the line above the cards
  const [lastAny, setLastAny] = useState<EvidenceView | null>(null)
  const [focusRecord, setFocusRecord] = useState<{ index: number; at: number } | null>(null)
  const [focusBar, setFocusBar] = useState<number | null>(null)
  const topRef = useRef<HTMLDivElement>(null)

  // THE PIECE ----------------------------------------------------------------
  useEffect(() => {
    let cancelled = false
    Promise.all([
      backendJson<CatalogComponent>(`/identities/${encodeURIComponent(identityId)}/compose`),
      backendJson<{ _id: string; group: string }[]>('/materials').catch(() => []),
      loadEvidenceOf(identityId, 'method=rebound_hammer&status=all').catch(() => []),
      loadEvidenceOf(identityId, 'method=core_compression&status=all').catch(() => []),
      sourceId ? backendJson<EvidenceView>(`/evidence/${encodeURIComponent(sourceId)}`) : Promise.resolve(null),
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
  }, [identityId, sourceId])

  // a correction carries the files of the record over (RL4): show them to keep or drop
  useEffect(() => {
    if (!correctId || editing || !corrected) return
    let cancelled = false
    loadAttachments(corrected._id)
      .then((rows) => { if (!cancelled) setCarried(rows.filter((row) => !row.removed)) })
      .catch(() => { if (!cancelled) setCarried([]) })
    return () => { cancelled = true }
  }, [correctId, editing, corrected])

  const methodName = state?.method
  const method = useMemo(
    () => registry?.methods.find((m) => m.name === methodName) ?? null,
    [registry, methodName],
  )
  const layout = method ? layoutOf(method.name) : null
  const actorRoot = useMemo(() => (registry ? actorRootOf(registry.methods) : null), [registry])
  // a component whose first version is not published has no state to record evidence about
  const snapshot = catalog?.snapshots?.length ? primarySnapshot(catalog) : null
  const snapshotId = snapshot ? String(snapshot._id ?? '') : ''
  const dataset = catalog?.identity.dataset ?? null
  const canContribute = rolesIn(dataset).includes('contributor')
    || (editing && Boolean(dataset) && moderates(dataset))
  // an edit is for the author of a draft or a moderator; the record decides
  const mayEdit = !editing || !corrected || canEditEvidence(
    corrected.status, corrected.recorded_by_user_id === me?._id, moderates(dataset))

  useEffect(() => {
    if (!dataset || !me || sourceId) return
    let cancelled = false
    myLatestRecord(null, dataset)
      .then((row) => { if (!cancelled) setLastAny(row) })
      .catch(() => { if (!cancelled) setLastAny(null) })
    return () => { cancelled = true }
  }, [dataset, me, sourceId])

  // a correction opens with the record's values
  useEffect(() => {
    if (!corrected || !registry || state) return
    const m = registry.methods.find((x) => x.name === corrected.method)
    if (m) setState(stateFromRecord(m, corrected, actorRoot))
  }, [corrected, registry, state, actorRoot])

  /** A new form: the profile of the recorder is proposed as the performer (8.133 d, 8.134 c). */
  const prefillPending = useRef(false)
  const freshState = useCallback((m: MethodInfo): FormState => {
    const next = initialState(m, identityId)
    if (me && actorRoot) next.performers = [meActor(me, actorRoot)]
    // the profile arrives after the form when the page is opened straight from a link
    prefillPending.current = !me
    return next
  }, [identityId, me, actorRoot])

  useEffect(() => {
    if (!prefillPending.current || !me || !actorRoot || !state || sourceId) return
    prefillPending.current = false
    if (state.performers.length === 0) setState({ ...state, performers: [meActor(me, actorRoot)] })
  }, [me, actorRoot, state, sourceId])

  const pick = (name: string) => {
    if (!registry) return
    const m = registry.methods.find((x) => x.name === name)
    if (m) {
      setState(freshState(m))
      setProblems([])
      setCreated(null)
    }
  }

  useEffect(() => {
    if (!initialMethod || sourceId || !registry || state || meLoading) return
    const m = registry.methods.find((x) => x.name === initialMethod)
    if (m) setState(freshState(m))
  }, [initialMethod, sourceId, registry, state, meLoading, freshState])

  const patch = useCallback((next: Partial<FormState>) => {
    setState((prev) => (prev ? { ...prev, ...next } : prev))
  }, [])

  /** The line above the cards: the method of my last record, filled in from it. */
  const repeatAny = () => {
    if (!registry || !lastAny) return
    const m = registry.methods.find((x) => x.name === lastAny.method)
    if (!m) return
    setProblems([])
    setCreated(null)
    setState(stateFromLast(m, identityId, lastAny, actorRoot))
    toast.success('Instrument, performers and standard filled in from your last record')
  }

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

  // THE ISSUES: what the form sees is missing, and what the server said ---------
  const formProblems = useMemo(() => (state && method ? formIssues(state, method) : []), [state, method])
  const serverProblems = useMemo(() => (method ? serverIssues(problems, method) : []), [problems, method])
  const issues = useMemo<Issue[]>(
    () => [...serverProblems, ...formProblems.filter((f) => !serverProblems.some((s) => s.target && s.target === f.target))],
    [serverProblems, formProblems],
  )
  const states = sectionStates(issues, {
    hasMethod: Boolean(method),
    files: state?.files.length ?? 0,
    notes: state?.notes ?? '',
    carried: carried.filter((e) => !dropped.has(e.index)).length,
  })

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
      const notes: string[] = []
      if (editing && corrected) {
        records = [await patchEvidence(corrected._id, editBody(items[0], method))]
      } else if (corrected) {
        const { identity_id: _unused, ...body } = items[0] as unknown as Record<string, unknown>
        void _unused
        const made = await backendJson<EvidenceView>(`/evidence/${encodeURIComponent(corrected._id)}/supersede`, {
          method: 'POST', body,
        })
        records = [made]
        notes.push(...await dropCarried(made, carried.filter((e) => dropped.has(e.index))))
      } else {
        records = await createBulk(items, false)
      }
      // a draft takes more files; so does a correction (its author, 8.142 a); a pending record does not (8.127)
      notes.push(...(!editing || records[0]?.status === 'draft'
        ? await attachFiles(state, records, layout.fanOut)
        : []))
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
        // the check step lists them with a jump link each
        window.setTimeout(() => jumpToSection('check'), 50)
      } else {
        const text = err instanceof BackendError ? err.message : 'Could not save the records'
        setProblems([{ path: '', message: text }])
        toast.error(text)
        window.setTimeout(() => jumpToSection('check'), 50)
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

  const submitAll = async () => {
    if (!created) return
    setSaving(true)
    try {
      for (const record of created.filter((r) => r.status === 'draft')) {
        await evidenceAction(record._id, 'submit')
      }
      toast.success('Submitted: a moderator of the dataset publishes it')
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
    const ok = await confirm({
      title: 'Go back to the form?',
      description: 'These drafts are deleted and the form keeps what you entered.',
      confirmLabel: 'Delete the drafts and go back',
      destructive: true,
    })
    if (!ok) return
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

  // JUMPS FROM THE CHECK STEP ----------------------------------------------------
  const jump = (issue: Issue) => {
    jumpToSection(issue.section)
    if (issue.record !== undefined && layout) {
      if (layout.fanOut === 'areas') setFocusRecord({ index: issue.record, at: Date.now() })
      if (layout.fanOut === 'single') setFocusBar(issue.record)
    }
    if (issue.target) {
      // the record or bar opens first, then the field is there to scroll to
      window.setTimeout(() => {
        const element = document.getElementById(issue.target ?? '')
        if (!element) return
        element.scrollIntoView({ behavior: 'smooth', block: 'center' })
        if (element instanceof HTMLElement && 'focus' in element) element.focus({ preventScroll: true })
      }, 120)
    }
  }

  // RENDER ----------------------------------------------------------------------
  const back = (
    <Link href={`/components/${encodeURIComponent(identityId)}`}
      className="inline-flex items-center gap-1 text-sm text-muted-foreground underline-offset-4 hover:underline">
      <ArrowLeft className="h-4 w-4" />Back to the component
    </Link>
  )
  const stepIds: FormStepId[] = state && method ? [...SECTION_ORDER, 'check'] : ['method']
  const active = useActiveStep(stepIds)

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

  if (!snapshot) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 p-4">
        {back}
        <h1 className="text-xl font-bold">Add evidence</h1>
        <p className="text-sm" role="status">
          #{identity.catalog_number} has no published state yet. Evidence is recorded about a state of the
          piece: come back once a moderator has published its first version.
        </p>
      </div>
    )
  }

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

  if (editing && corrected && !mayEdit) {
    return (
      <div className="mx-auto max-w-3xl space-y-3 p-4">
        {back}
        <h1 className="text-xl font-bold">Edit a record</h1>
        <p className="text-sm" role="status">
          This record cannot be edited here: only the author or a moderator of the dataset changes a draft,
          only a moderator a record waiting for review, and a published record is corrected instead.
        </p>
      </div>
    )
  }

  if (created) {
    const drafts = created.filter((r) => r.status === 'draft')
    return (
      <div ref={topRef} className="mx-auto max-w-3xl space-y-4 p-4 pb-24">
        {dialog}
        {back}
        <h1 className="text-xl font-bold">
          {editing ? 'Check the record' : corrected ? 'Check the correction' : 'Check the records'}
        </h1>
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
              <Button disabled={saving} onClick={() => void submitAll()}>
                Submit {drafts.length > 1 ? `all ${drafts.length}` : ''}
              </Button>
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

  const methods = orderMethods(registry.methods)
  const help = registry.help
  const hasMeActor = !!state && state.performers.some((a) => isMe(a, me))
  const date = state && method && method.context_time !== 'sampled_at'
  const mode = editing ? 'Edit a record' : corrected ? 'Correct a record' : 'Add evidence'
  const modeChip = editing && corrected
    ? `Editing a ${corrected.status} record`
    : corrected
      ? `Correction of the ${vocabLabel(EVIDENCE_METHOD_LABELS, corrected.method).toLowerCase()} of ${formatDay(corrected.observed_at)}`
      : null

  const whatTitle = !layout ? 'What was found'
    : layout.fanOut === 'areas' ? `${layout.recordLabel.charAt(0).toUpperCase()}${layout.recordLabel.slice(1)}s`
      : layout.fanOut === 'observations' ? 'Findings'
        : layout.fanOut === 'pieces' ? 'The claim' : 'The layout'
  const titles: Record<SectionId, string> = {
    method: 'Method', who: 'Who and when', what: whatTitle, files: 'Files', notes: 'Notes',
  }
  const countOf = (section: SectionId) => issuesOf(issues, section).length
  const steps: Step[] = stepIds.map((id) => (id === 'check'
    ? { id, title: 'Check and save', state: 'check' as const, count: issues.length }
    : { id, title: titles[id], state: states[id], count: countOf(id) }))
  const notices = state && editing && corrected
    ? verificationNotices(corrected, state.performers.map((a) => String(a.user_id ?? '')).filter(Boolean))
    : []

  const savesText = (() => {
    if (!state || !layout) return ''
    const count = layout.fanOut === 'areas' ? plural(state.records.length, layout.recordLabel)
      : layout.fanOut === 'observations' ? plural(state.observations.length, 'finding')
        : layout.fanOut === 'pieces' ? plural(state.pieces.length, 'claim')
          : `1 layout with ${plural(Array.isArray(state.records[0]?.payload.bars) ? (state.records[0].payload.bars as unknown[]).length : 0, 'bar')}`
    const files = state.files.length + (layout.fanOut === 'observations' ? state.photos.length : 0)
    const version = snapshot.version ? `, version ${snapshot.version}` : ''
    const withFiles = files > 0 ? `, with ${plural(files, 'file')}` : ''
    if (editing && corrected) return `Saves the changes to this ${corrected.status} record on ${title}${version}${withFiles}.`
    if (corrected) {
      return `Saves a correction on ${title}${version}${withFiles}${carried.length - dropped.size > 0 ? `, ${plural(carried.length - dropped.size, 'file')} carried over` : ''}. The corrected record stays until a moderator publishes this one.`
    }
    return `Saves ${count} as ${state.records.length + state.observations.length + state.pieces.length > 1 || layout.fanOut === 'single' ? 'drafts' : 'a draft'} on ${title}${version}${withFiles}.`
  })()

  const saveLabel = editing ? 'Save the changes and check' : corrected ? 'Save the correction and check' : 'Save as drafts and check'
  const claimErrors = Object.fromEntries(problems
    .filter((p) => p.path.startsWith('payload.'))
    .map((p) => [p.path.slice(8), [p.message]]))
  const barErrors = problems.filter((p) => p.path.startsWith('payload.bars')).map((p) => p.message)

  return (
    <div ref={topRef} className="mx-auto max-w-5xl p-4 pb-28">
      {dialog}
      <div className="mb-4 space-y-2">
        {back}
        <div>
          <h1 className="text-xl font-bold">{mode}</h1>
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
            <span>{title}{dataset ? ` (${dataset})` : ''}</span>
            {snapshot.version ? (
              <span className="rounded-full border border-border px-2 py-0.5 text-xs">version {snapshot.version}</span>
            ) : null}
            {modeChip && <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{modeChip}</span>}
          </p>
          {editing && corrected && (
            <p className="mt-1 text-xs text-muted-foreground">
              The record keeps its status{corrected.status === 'draft' ? ' and its files; you can add more files' : ' and its files'}.
            </p>
          )}
          {corrected && !editing && (
            <p className="mt-1 text-xs text-muted-foreground">
              The corrected record stays; the new one replaces it in the lists and the fold once a moderator publishes it.
            </p>
          )}
        </div>
      </div>

      <ProgressLine steps={steps} active={active} />
      <div className="mt-4 lg:grid lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-6">
        <Outline steps={steps} active={active} />
        <div className="min-w-0 space-y-5">
          <FormSection
            id="method" number={1} title="Method" state={states.method}
            actions={!corrected && lastAny && registry.methods.some((x) => x.name === lastAny.method) ? (
              <>
                <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={repeatAny}>
                  <History className="mr-1 h-3.5 w-3.5" />Repeat from my last record
                </Button>
                <span className="hidden text-xs text-muted-foreground sm:inline">
                  {vocabLabel(EVIDENCE_METHOD_LABELS, lastAny.method)}, {formatDay(lastAny.observed_at)}
                </span>
              </>
            ) : null}
          >
            <MethodPicker methods={methods} value={state?.method ?? null} onPick={pick} locked={Boolean(corrected)} />
          </FormSection>

          {state && method && layout && (
            <>
              <FormSection
                id="who" number={2} title="Who and when" state={states.who} count={countOf('who')}
                actions={!corrected ? (
                  <Button type="button" variant="outline" size="sm" className="h-8 text-xs" disabled={loadingLast}
                    onClick={() => void loadLast()}>
                    {loadingLast ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : <History className="mr-1 h-3.5 w-3.5" />}
                    Repeat from my last record
                  </Button>
                ) : null}
              >
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
                    <DateField id="observed-at" value={state.observedAt}
                      onChange={(observedAt) => patch({ observedAt })} className="max-w-72" />
                  </Field>
                )}
                <StandardLine
                  method={method}
                  code={state.standardCode}
                  year={state.standardYear}
                  errors={envelopeProblems('standard')}
                  onChange={(standardCode, standardYear) => patch({ standardCode, standardYear })}
                />
                {hasMeActor && !editing && (
                  <div className="flex items-start gap-2">
                    <Checkbox id="self-attested" checked={state.selfAttested}
                      onCheckedChange={(c) => patch({ selfAttested: c === true })} className="mt-0.5" />
                    <Label htmlFor="self-attested" className="text-sm font-normal">
                      I performed this and stand by the result
                    </Label>
                  </div>
                )}
              </FormSection>

              <FormSection id="what" number={3} title={whatTitle} state={states.what} count={countOf('what')}>
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
                    missing={(index) => formProblems.filter((i) => i.record === index).map((i) => i.message)}
                    sharedState={serverProblems.some((i) => i.target?.startsWith('record-shared')) ? 'error'
                      : formProblems.some((i) => i.target?.startsWith('record-shared')) ? 'missing' : 'done'}
                    rebounds={pairingCandidates(rebounds, cores, '', [])}
                    help={help}
                    onPickPoint={(recordKey) => setPicker({ mode: 'point', recordKey })}
                    onPickGrid={(recordKey) => setPicker({ mode: 'grid', recordKey })}
                    onAddLocations={() => setPicker({ mode: 'locations' })}
                    single={Boolean(corrected)}
                    focusRecord={focusRecord}
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
                    missing={(index) => formProblems.filter((i) => i.record === index).map((i) => i.message)}
                    focusRecord={focusRecord}
                  />
                )}

                {(layout.fanOut === 'pieces' || layout.fanOut === 'single') && state.records[0] && (
                  <div className="space-y-4">
                    <SchemaFields
                      schema={method.payload_schema}
                      root={method.payload_schema}
                      value={state.records[0].payload}
                      onChange={(payload) => patch({ records: [{ ...state.records[0], payload }] })}
                      idPrefix="claim"
                      layout={layout}
                      errors={claimErrors}
                      overrides={layout.fanOut === 'single' ? {
                        bars: ({ parent, setParent }) => (
                          <BarsEditor
                            id="claim-bars"
                            bars={Array.isArray(parent.bars) ? (parent.bars as FormObject[]) : []}
                            onChange={(bars) => setParent({ ...parent, bars })}
                            serverErrors={barErrors}
                            focusBar={focusBar}
                          />
                        ),
                      } : undefined}
                    />
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
                      <>
                        <PositionField
                          id="layout-position"
                          position={state.records[0].position}
                          onChange={(position) => patch({ records: [{ ...state.records[0], position }] })}
                          onPick={() => undefined}
                          noPoint
                          errors={envelopeProblems('position')}
                          help={help('PositionInput', 'description')}
                        />
                        <p className="text-xs text-muted-foreground">
                          A layout belongs to one version: the bars are in the stored coordinates (millimetres) of
                          {snapshot.version ? ` version ${snapshot.version}` : ' the version'} you see on the component
                          page. Another version needs a layout of its own.
                        </p>
                      </>
                    )}
                  </div>
                )}
              </FormSection>

              <FormSection id="files" number={4} title="Files" state={states.files}
                summary={state.files.length > 0 ? plural(state.files.length, 'file') : undefined}>
                {corrected && !editing && carried.length > 0 && (
                  <CarriedFiles entries={carried} dropped={dropped} onChange={setDropped} />
                )}
                {(!editing || corrected?.status === 'draft') ? (
                  <FilesField
                    files={state.files}
                    onChange={(files) => patch({ files })}
                    help={help(...UPLOAD_HELP)}
                    label={layout.fanOut === 'observations' ? 'Other files (a report, a drawing)'
                      : corrected && !editing ? 'Further files for the correction' : 'Files for all records'}
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    A record that waits for review keeps its files; add or remove them on the record after saving.
                  </p>
                )}
              </FormSection>

              <FormSection id="notes" number={5} title="Notes" state={states.notes}>
                <Textarea id="notes" rows={3} value={state.notes} aria-label="Notes"
                  placeholder="Anything a reader of this record should know"
                  onChange={(e) => patch({ notes: e.target.value })} />
              </FormSection>

              <FormSection id="check" number={6} title="Check and save" state="check">
                <CheckSection
                  summary={savesText}
                  notices={notices}
                  issues={issues}
                  titles={titles}
                  onJump={jump}
                  onSave={() => void save()}
                  saving={saving}
                  saveLabel={saveLabel}
                />
              </FormSection>

              <div className="sticky bottom-0 z-30 -mx-4 flex flex-wrap items-center gap-2 border-t border-border bg-background/95 px-4 py-2.5 backdrop-blur lg:mx-0 lg:rounded-md lg:border">
                <Button onClick={() => void save()} disabled={saving}>
                  {saving ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                  {saveLabel}
                </Button>
                {issues.length > 0 ? (
                  <Button type="button" variant="ghost" size="sm" className="h-8 text-xs text-amber-800 dark:text-amber-300"
                    onClick={() => jumpToSection('check')}>
                    {plural(issues.length, 'thing')} to look at
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground">Nothing missing</span>
                )}
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
      </div>
    </div>
  )
}

/** The standard of the method folded to one line ("Standard: EN 12504-2 (2019) - change"), 8.134 c. */
function StandardLine({
  method,
  code,
  year,
  errors,
  onChange,
}: {
  method: MethodInfo
  code: string
  year: string
  errors: string[]
  onChange: (code: string, year: string) => void
}) {
  const standard = method.default_standard
  const typed = code.trim() !== '' || year.trim() !== ''
  const [open, setOpen] = useState(false)
  const words = standard ? `${standard.code}${standard.year ? ` (${standard.year})` : ''}` : null

  if (!open && !typed && errors.length === 0) {
    return (
      <p className="flex flex-wrap items-center gap-x-2 text-sm">
        <span className="text-muted-foreground">Standard:</span>
        <span>{words ?? 'none stated'}</span>
        <Button type="button" variant="link" size="sm" className="h-6 px-0 text-xs" onClick={() => setOpen(true)}>
          {words ? 'change' : 'add one'}
        </Button>
      </p>
    )
  }
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_6rem] gap-2">
        <Field id="standard-code" label="Standard"
          help={words ? `Defaults to ${words}` : ''} errors={errors}>
          <Input id="standard-code" value={code}
            placeholder={standard?.code ?? 'e.g. EN 12504-2'}
            onChange={(e) => onChange(e.target.value, year)} />
        </Field>
        <Field id="standard-year" label="Year">
          <Input id="standard-year" inputMode="numeric" value={year}
            placeholder={standard?.year ? String(standard.year) : ''}
            onChange={(e) => onChange(code, e.target.value)} />
        </Field>
      </div>
      {words && (
        <Button type="button" variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
          onClick={() => { onChange('', ''); setOpen(false) }}>
          <Undo2 className="mr-1 h-3 w-3" />Use the default: {words}
        </Button>
      )}
    </div>
  )
}

/** The files of the corrected record that come over to the correction: keep or drop each (RL4). */
function CarriedFiles({
  entries,
  dropped,
  onChange,
}: {
  entries: AttachmentEntry[]
  dropped: Set<number>
  onChange: (next: Set<number>) => void
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium">Files carried over from the corrected record</p>
      <ul className="space-y-1">
        {entries.map((entry) => {
          const off = dropped.has(entry.index)
          return (
            <li key={entry.index} className="flex items-center justify-between gap-2 rounded-md border border-border px-2 py-1 text-sm">
              <span className={`flex min-w-0 items-center gap-1.5 ${off ? 'text-muted-foreground line-through' : ''}`}>
                <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{entry.name || `File ${entry.index + 1}`}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{Math.max(1, Math.round(entry.size / 1000))} kB</span>
              </span>
              <Button
                type="button" variant="ghost" size="sm" className="h-7 text-xs"
                onClick={() => {
                  const next = new Set(dropped)
                  if (off) next.delete(entry.index)
                  else next.add(entry.index)
                  onChange(next)
                }}
              >
                {off ? 'Keep' : 'Remove'}
              </Button>
            </li>
          )
        })}
      </ul>
      <p className="text-xs text-muted-foreground">
        The correction carries these files unless you remove them; the corrected record keeps its own.
      </p>
    </div>
  )
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

/** Remove the carried files the author dropped from the new correction (matched by checksum). */
async function dropCarried(made: EvidenceView, dropped: AttachmentEntry[]): Promise<string[]> {
  const notes: string[] = []
  const have = ((made.attachments ?? []) as AttachmentEntry[]).filter((e) => !e.removed)
  for (const entry of dropped) {
    const twin = have.find((e) => e.sha256 === entry.sha256 && e.name === entry.name)
    if (!twin) continue
    try {
      await removeAttachment(made._id, twin.index)
    } catch (err) {
      notes.push(`${entry.name ?? 'A file'} could not be removed from the correction: ${err instanceof Error ? err.message : 'failed'}. Remove it on the record below.`)
    }
  }
  return notes
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
