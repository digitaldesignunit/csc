'use client'

/**
 * A visual inspection (decision 7.9, 7.4): the overall grade and the
 * findings that apply to the piece's material group, one record each
 * (fan-out), each with the photos taken for it. A photo that shows several
 * findings is attached to each of them (one upload, decision 7.3).
 */
import { useMemo, useState } from 'react'
import { ImagePlus, Plus, Trash2 } from 'lucide-react'

import { Field, NativeSelect } from '@/components/evidence/controls'
import {
  newKey,
  newObservation,
  type ObservationState,
  type PhotoItem,
} from '@/components/evidence/form/state'
import SnapshotPhotoCapture from '@/components/photos/SnapshotPhotoCapture'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { MethodInfo, QuantityInfo } from '@/lib/evidence/api'
import { quantityLabel } from '@/lib/evidence/format'
import { resolve } from '@/lib/evidence/schema'
import { conditionLabel } from '@/components/components/componentDetailShared'

const MAX_PHOTOS_PER_FINDING = 8

/** The quantities a piece of this material group can be inspected for. */
export function inspectionQuantities(
  method: MethodInfo,
  quantities: QuantityInfo[],
  materialGroup: string | null,
): QuantityInfo[] {
  const observation = resolve({ $ref: '#/$defs/VisualObservation' }, method.payload_schema).schema
  const names = (observation.properties?.quantity?.enum ?? method.summary_quantities) as string[]
  return names
    .map((name) => quantities.find((q) => q.name === name))
    .filter((q): q is QuantityInfo => !!q)
    .filter((q) => !q.applies_to || !materialGroup || q.applies_to.includes(materialGroup))
}

function ValueInput({
  id,
  quantity,
  value,
  onChange,
}: {
  id: string
  quantity: QuantityInfo | undefined
  value: string
  onChange: (next: string) => void
}) {
  if (!quantity) return <p className="text-xs text-muted-foreground">Pick what was observed first.</p>
  if (quantity.name === 'crack_width') {
    return (
      <div className="flex items-center gap-2">
        <Input id={id} inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} className="max-w-32" />
        <span className="text-sm text-muted-foreground">mm</span>
      </div>
    )
  }
  const grade = quantity.name === 'condition_grade'
  return (
    <div role="radiogroup" aria-label={quantityLabel(quantity.name)} className="space-y-1">
      <div className="flex gap-1.5">
        {['0', '1', '2', '3'].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            onClick={() => onChange(n)}
            className={`h-10 w-12 rounded-md border text-base font-medium ${
              value === n ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted/50'
            }`}
          >
            {n}
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {grade
          ? `${conditionLabel(0)}  ...  ${conditionLabel(3)}`
          : '0 none  ...  3 severe'}
      </p>
    </div>
  )
}

export default function InspectionEditor({
  idPrefix,
  method,
  quantities,
  materialGroup,
  observations,
  photos,
  onObservations,
  onPhotos,
  errors,
}: {
  idPrefix: string
  method: MethodInfo
  quantities: QuantityInfo[]
  materialGroup: string | null
  observations: ObservationState[]
  photos: PhotoItem[]
  onObservations: (next: ObservationState[]) => void
  onPhotos: (next: PhotoItem[]) => void
  /** problems of the server by observation index */
  errors: (index: number) => string[]
}) {
  const options = useMemo(
    () => inspectionQuantities(method, quantities, materialGroup),
    [method, quantities, materialGroup],
  )
  const describe = resolve({ $ref: '#/$defs/VisualObservation' }, method.payload_schema).schema
  const [open, setOpen] = useState<string | null>(null)

  const update = (key: string, patch: Partial<ObservationState>) =>
    onObservations(observations.map((o) => (o.key === key ? { ...o, ...patch } : o)))

  const setFiles = (observation: ObservationState, files: File[]) => {
    const own = photos.filter((p) => observation.photoIds.includes(p.id))
    const kept = own.filter((p) => files.includes(p.file))
    const added = files.filter((f) => !own.some((p) => p.file === f))
    const fresh = added.map((file) => ({ id: newKey(), file }))
    const removedIds = own.filter((p) => !files.includes(p.file)).map((p) => p.id)
    const assigned = [...kept.map((p) => p.id), ...fresh.map((p) => p.id)]
    const stillUsed = new Set(
      observations.filter((o) => o.key !== observation.key).flatMap((o) => o.photoIds),
    )
    onPhotos([
      ...photos.filter((p) => !removedIds.includes(p.id) || stillUsed.has(p.id)),
      ...fresh,
    ])
    update(observation.key, { photoIds: assigned })
  }

  const toggleExisting = (observation: ObservationState, photoId: string) => {
    update(observation.key, {
      photoIds: observation.photoIds.includes(photoId)
        ? observation.photoIds.filter((id) => id !== photoId)
        : [...observation.photoIds, photoId],
    })
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        One record per finding, so each can be corrected and moderated on its own. Photos belong to the finding they document.
      </p>
      {observations.map((observation, index) => {
        const quantity = options.find((q) => q.name === observation.quantity)
        const own = photos.filter((p) => observation.photoIds.includes(p.id))
        const others = photos.filter((p) => !observation.photoIds.includes(p.id))
        const id = `${idPrefix}-${observation.key}`
        const problems = errors(index)
        return (
          <fieldset key={observation.key} className="space-y-3 rounded-md border border-border/70 p-3">
            <legend className="px-1 text-xs font-semibold text-muted-foreground">
              Finding {index + 1}
            </legend>
            <Field id={`${id}-quantity`} label="What was observed"
              help={describe.properties?.quantity?.description ?? ''} required errors={problems}>
              <NativeSelect
                id={`${id}-quantity`}
                value={observation.quantity}
                onChange={(next) => update(observation.key, { quantity: next, value: '' })}
                options={options.map((q) => ({ value: q.name, label: quantityLabel(q.name) }))}
              />
            </Field>
            <Field id={`${id}-value`} label={quantity?.name === 'crack_width' ? 'Widest crack' : 'Severity or grade'}
              help={describe.properties?.value?.description ?? ''} required>
              <ValueInput
                id={`${id}-value`}
                quantity={quantity}
                value={observation.value}
                onChange={(next) => update(observation.key, { value: next })}
              />
            </Field>
            <Field id={`${id}-note`} label="Note" help={describe.properties?.note?.description ?? ''}>
              <Textarea id={`${id}-note`} rows={2} value={observation.note}
                onChange={(e) => update(observation.key, { note: e.target.value })} />
            </Field>
            <div className="space-y-2">
              <p className="text-xs font-medium">Photos of this finding</p>
              <SnapshotPhotoCapture
                mode="staged"
                files={own.map((p) => p.file)}
                onFilesChange={(files) => setFiles(observation, files)}
                maxPhotos={MAX_PHOTOS_PER_FINDING}
              />
              {others.length > 0 && (
                <div className="space-y-1">
                  <Button type="button" variant="ghost" size="sm" className="h-7 text-xs"
                    onClick={() => setOpen(open === observation.key ? null : observation.key)}>
                    <ImagePlus className="mr-1 h-3.5 w-3.5" />
                    Photo also shows this finding ({others.length} other{others.length === 1 ? '' : 's'})
                  </Button>
                  {open === observation.key && (
                    <ul className="flex flex-wrap gap-1.5">
                      {others.map((p) => (
                        <li key={p.id}>
                          <button type="button" className="rounded-md border px-2 py-1 text-xs hover:bg-muted/50"
                            onClick={() => toggleExisting(observation, p.id)}>
                            {p.file.name}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {own.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  Shared with other findings:{' '}
                  {own.filter((p) => observations.some((o) => o.key !== observation.key && o.photoIds.includes(p.id))).length}
                </p>
              )}
            </div>
            {observations.length > 1 && (
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs text-muted-foreground"
                onClick={() => onObservations(observations.filter((o) => o.key !== observation.key))}>
                <Trash2 className="mr-1 h-3 w-3" />Remove finding
              </Button>
            )}
          </fieldset>
        )
      })}
      <Button type="button" variant="outline" size="sm" className="h-8 text-xs"
        onClick={() => onObservations([...observations, newObservation()])}>
        <Plus className="mr-1 h-3.5 w-3.5" />Add finding
      </Button>
    </div>
  )
}
