'use client'

/**
 * "Cut from ...": record a piece cut from this component, or merged from
 * it and others (spec section 3.1.2, 3.1.3, section 7.6 entry points;
 * decisions 7.5, 8.8, 8.31 -- 8.34). `POST /identities` with
 * `parent_identities` creates the child and its v0 draft --- an authored
 * box from L x W x H; the child takes over everything it does not state.
 * The draft is submitted at once; for a moderator that also publishes it,
 * and only then does the parent leave circulation (split / merged).
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import type { ComponentIdentity } from '@/generated/CatalogModels'
import type { DatasetView } from '@/generated/AccessModels'
import { ORIGINAL_FUNCTION_LABELS, type OriginalFunction } from '@/generated/Vocab'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { OptionalDateInput } from '@/components/ui/optional-date-input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { backendJson } from '@/lib/backend'
import { canonicalizeBoxAxesMm, parseDimensionMm, sanitizeDimensionInput } from '@/lib/catalogCreate'
import { dateOnlyToIso } from '@/lib/lineage'
import { uuidFromScan } from '@/lib/scanIds'
import { Field, VocabSelect } from './fields'

const IDENTITY_PLACEMENT = { o: [0, 0, 0], x: [1, 0, 0], y: [0, 1, 0], z: [0, 0, 1] }

type Created = { identity: { _id: string }; snapshot: { _id: string } }

/** An authored box proxy (App. B); a column stands on its longest side. */
function authoredBox(lengthMm: number, widthMm: number, heightMm: number, column: boolean) {
  const { xMm, yMm, zMm } = canonicalizeBoxAxesMm(lengthMm, widthMm, heightMm, column ? 'column' : undefined)
  return {
    meshes: [],
    point_clouds: [],
    proxies: [{
      primitive: 'box',
      role: 'primary',
      params: { size: [xMm, yMm, zMm] },
      placement: IDENTITY_PLACEMENT,
      fit: { method: 'authored' },
      regions: [],
    }],
  }
}

type Props = {
  parent: ComponentIdentity
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function CutFromDialog({ parent, open, onOpenChange }: Props) {
  const router = useRouter()
  const [datasets, setDatasets] = useState<DatasetView[]>([])
  const [dataset, setDataset] = useState('')
  const [tag, setTag] = useState('')
  const [others, setOthers] = useState('')
  const [name, setName] = useState('')
  const [fn, setFn] = useState<OriginalFunction | null>(null)
  const [dims, setDims] = useState({ l: '', w: '', h: '' })
  const [cutOn, setCutOn] = useState('')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    backendJson<DatasetView[]>('/datasets')
      .then((rows) => {
        if (cancelled) return
        const writable = rows.filter((d) => d.roles.includes('contributor'))
        setDatasets(writable)
        setDataset((current) =>
          current || (writable.some((d) => d._id === parent.dataset) ? parent.dataset : writable[0]?._id ?? ''))
      })
      .catch(() => setDatasets([]))
    return () => {
      cancelled = true
    }
  }, [open, parent.dataset])

  const submit = async () => {
    setError(null)
    const id = tag.trim() ? uuidFromScan(tag) : null
    if (tag.trim() && !id) {
      setError('Tag: give the id on the new tag or its link.')
      return
    }
    const extra: string[] = []
    for (const raw of others.split(/[\s,;]+/).filter(Boolean)) {
      const pid = uuidFromScan(raw)
      if (!pid) {
        setError(`Further parent: ${raw} is not a component id or link.`)
        return
      }
      if (pid !== parent._id && !extra.includes(pid)) extra.push(pid)
    }
    const [l, w, h] = [parseDimensionMm(dims.l), parseDimensionMm(dims.w), parseDimensionMm(dims.h)]
    if (![l, w, h].every((v) => Number.isFinite(v) && v > 0)) {
      setError('Give length, width and height in mm.')
      return
    }
    if (!dataset) {
      setError('You contribute to no dataset; ask its moderator for the contributor role.')
      return
    }
    const effective = dateOnlyToIso(cutOn)
    const column = (fn ?? parent.original_function) === 'IfcColumn'
    setBusy(true)
    try {
      const created = await backendJson<Created>('/identities', {
        method: 'POST',
        body: {
          ...(id ? { id } : {}),
          dataset,
          parent_identities: [parent._id, ...extra],
          ...(fn ? { original_function: fn } : {}),
          snapshot: {
            name: name.trim() || null,
            geometry: authoredBox(l, w, h, column),
            notes: notes.trim() || null,
            ...(effective ? { effective_from: effective, effective_from_precision: 'day' } : {}),
          },
        },
      })
      // the piece exists now: whatever submit says, go to it
      try {
        const submitted = await backendJson<{ status?: string }>(
          `/snapshots/${created.snapshot._id}/submit?publish=1&promote=1`, { method: 'POST' })
        toast.success(submitted?.status === 'published'
          ? 'Piece recorded and published'
          : 'Piece recorded; a moderator publishes it')
      } catch (err) {
        toast.error(`Piece recorded as a draft; submitting failed: ${err instanceof Error ? err.message : err}`)
      }
      onOpenChange(false)
      router.push(`/components/${created.identity._id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Recording the piece failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next) }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Cut a piece from #{parent.catalog_number}</DialogTitle>
          <DialogDescription>
            The piece takes over origin, material, manufacture and function from this component
            and follows later corrections. This component leaves circulation once the piece is
            published.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Field label="Tag of the new piece" htmlFor="cut-tag"
            hint="Scan or paste the id on the new tag. Empty: a new id is generated.">
            <Input id="cut-tag" value={tag} onChange={(event) => setTag(event.target.value)}
              placeholder="Id or link" />
          </Field>
          <Field label="Dataset" htmlFor="cut-dataset">
            <Select value={dataset} onValueChange={setDataset}>
              <SelectTrigger id="cut-dataset" className="w-full">
                <SelectValue placeholder="No dataset you contribute to" />
              </SelectTrigger>
              <SelectContent>
                {datasets.map((d) => (
                  <SelectItem key={d._id} value={d._id}>{d.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Name" htmlFor="cut-name">
            <Input id="cut-name" value={name} onChange={(event) => setName(event.target.value)}
              placeholder="Empty: the catalog number" />
          </Field>
          <Field label="Size (mm)" hint="An authored box; scans replace it later.">
            <div className="grid grid-cols-3 gap-2">
              {(['l', 'w', 'h'] as const).map((key) => (
                <Input key={key} inputMode="decimal" aria-label={{ l: 'Length', w: 'Width', h: 'Height' }[key]}
                  placeholder={{ l: 'Length', w: 'Width', h: 'Height' }[key]} value={dims[key]}
                  onChange={(event) => setDims((d) => ({ ...d, [key]: sanitizeDimensionInput(event.target.value) }))} />
              ))}
            </div>
          </Field>
          <Field label="Original function" htmlFor="cut-function">
            <VocabSelect id="cut-function" labels={ORIGINAL_FUNCTION_LABELS} value={fn} onChange={setFn}
              allowNone noneLabel={`Same as the parent (${ORIGINAL_FUNCTION_LABELS[parent.original_function]})`} />
          </Field>
          <OptionalDateInput id="cut-on" label="Cut on (empty: today)" value={cutOn} onChange={setCutOn} />
          <Field label="Merged with (optional)" htmlFor="cut-others"
            hint="Ids or links of further pieces this one is made from, one per line.">
            <Textarea id="cut-others" rows={2} value={others} onChange={(event) => setOthers(event.target.value)} />
          </Field>
          <Field label="Notes" htmlFor="cut-notes">
            <Textarea id="cut-notes" rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </Field>
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => void submit()} disabled={busy}>Record piece</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
