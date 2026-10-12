'use client'

/**
 * The details of a reinforcement layout in its card (RL10, RL5; decisions
 * 8.142, 8.106): the basis, the drawing it comes from (title, date, reference,
 * link and the day the link was read) or the scanner, the accuracy note
 * (signed-in viewers only: the API leaves it out for the public) and the
 * number of bars. A moderator of the dataset fills the empty document fields
 * of a published layout once, in place; a field that is set changes only
 * through a correction.
 */
import { useState } from 'react'
import { FilePen, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Field } from '@/components/evidence/controls'
import { Button } from '@/components/ui/button'
import { DateField } from '@/components/ui/date-field'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import type { EvidenceView } from '@/generated'
import { BackendError } from '@/lib/backend'
import { patchEvidence } from '@/lib/evidence/api'
import {
  DOCUMENT_LABELS,
  emptyDocumentFields,
  fillBody,
  fillProblems,
  type DocumentField,
  type DocumentValues,
} from '@/lib/evidence/layoutDocument'
import { useMe } from '@/lib/me'
import { formatDateAtPrecision } from '@/components/components/componentDetailShared'

type Block = Record<string, unknown>

const precisionOfText = (value: string) => (value.length === 4 ? 'year' : value.length === 7 ? 'month' : 'day')

export default function LayoutDetails({
  record,
  dataset,
  onChanged,
}: {
  record: EvidenceView
  dataset: string | null | undefined
  onChanged: () => void
}) {
  const { moderates } = useMe()
  const payload = (record.payload ?? {}) as Record<string, unknown>
  const document = (payload.document ?? null) as Block | null
  const instrument = (payload.instrument ?? null) as Block | null
  const note = typeof payload.accuracy_note === 'string' ? payload.accuracy_note.trim() : ''
  const bars = Array.isArray(payload.bars) ? payload.bars.length : 0
  const open = emptyDocumentFields(payload)
  const mayFill = record.status === 'published' && !record.superseded_by && moderates(dataset) && open.length > 0
  const [dialog, setDialog] = useState(false)

  const rows: [string, React.ReactNode][] = []
  if (payload.basis) rows.push(['Basis', String(payload.basis)])
  if (document) {
    if (document.title) rows.push(['Drawing', String(document.title)])
    if (document.date) rows.push(['Drawing date', formatDateAtPrecision(String(document.date), precisionOfText(String(document.date)))])
    if (document.reference) rows.push(['Reference', String(document.reference)])
    // the link and the day it was read are the card's own "Source" line
  }
  if (instrument) {
    const parts = [instrument.kind, instrument.manufacturer, instrument.model].filter((p) => typeof p === 'string' && p).join(' ')
    if (parts) rows.push(['Instrument', parts])
    if (instrument.last_calibration_at) rows.push(['Calibrated', String(instrument.last_calibration_at)])
    if (instrument.site_calibration) rows.push(['On-site calibration', String(instrument.site_calibration)])
  }
  if (bars) rows.push(['Bars', String(bars)])
  if (note) rows.push(['Accuracy', <span key="n" className="whitespace-pre-line">{note}</span>])

  if (rows.length === 0 && !mayFill) return null
  return (
    <div className="space-y-2">
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs" aria-label="The layout">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {mayFill && (
        <>
          <Button type="button" variant="outline" size="sm" className="h-8 text-xs" onClick={() => setDialog(true)}>
            <FilePen className="mr-1 h-3.5 w-3.5" />Fill in the document details
          </Button>
          <FillDialog
            open={dialog}
            onOpenChange={setDialog}
            record={record}
            fields={open}
            onSaved={() => { setDialog(false); onChanged() }}
          />
        </>
      )}
    </div>
  )
}

function FillDialog({
  open,
  onOpenChange,
  record,
  fields,
  onSaved,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  record: EvidenceView
  fields: DocumentField[]
  onSaved: () => void
}) {
  const [typed, setTyped] = useState<Partial<DocumentValues>>({})
  const [problems, setProblems] = useState<Partial<Record<DocumentField, string>>>({})
  const [saving, setSaving] = useState(false)
  const [general, setGeneral] = useState<string | null>(null)
  const payload = record.payload ?? {}

  const save = async () => {
    const found = fillProblems(payload, typed)
    setProblems(found)
    setGeneral(null)
    if (Object.keys(found).length > 0) return
    const body = fillBody(payload, typed)
    if (Object.keys(body.payload.document).length === 0) {
      setGeneral('Fill in at least one field.')
      return
    }
    setSaving(true)
    try {
      await patchEvidence(record._id, body)
      toast.success('The document details are saved. A value that is set now changes only through a correction.')
      onSaved()
    } catch (err) {
      setGeneral(err instanceof BackendError ? err.message : 'Could not save the details')
    } finally {
      setSaving(false)
    }
  }

  const set = (key: DocumentField, value: string) => setTyped((prev) => ({ ...prev, [key]: value }))
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Document details of the layout</DialogTitle>
          <DialogDescription>
            Fill in what is still empty. The record is published: a value you set here stays, and changing it
            later means a correction. The change is recorded in the change log.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {fields.map((key) => (
            <Field key={key} id={`fill-${key}`} label={DOCUMENT_LABELS[key]}
              required={key === 'title' && !(record.payload as { document?: unknown } | undefined)?.document}
              errors={problems[key] ? [problems[key] as string] : []}>
              {key === 'date' ? (
                <DateField id="fill-date" value={typed.date ?? ''} precisions={['year', 'month', 'day']}
                  onChange={(v) => set('date', v)} />
              ) : key === 'retrieved_at' ? (
                <DateField id="fill-retrieved_at" value={typed.retrieved_at ?? ''} onChange={(v) => set('retrieved_at', v)} />
              ) : (
                <Input id={`fill-${key}`} value={typed[key] ?? ''}
                  placeholder={key === 'url' ? 'https://...' : undefined}
                  inputMode={key === 'url' ? 'url' : undefined}
                  onChange={(e) => set(key, e.target.value)} />
              )}
            </Field>
          ))}
          {general && <p className="text-xs text-destructive" role="alert">{general}</p>}
        </div>
        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="button" onClick={() => void save()} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
