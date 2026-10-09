'use client'

/**
 * Step "Details" of the snapshot form: what the piece is (new component
 * only), and the fields every snapshot carries. A cut inherits what it does
 * not state (spec 3.1.2), so it asks only for the function it may override.
 */
import type { DatasetView } from '@/generated/AccessModels'
import type { Material } from '@/generated/LineageModels'
import { ORIGINAL_FUNCTION_LABELS } from '@/generated/Vocab'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { OptionalDateInput } from '@/components/ui/optional-date-input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { Field, OriginFields, VocabSelect } from '@/components/lineage/fields'
import { emptyOrigin } from '@/lib/lineage'
import type { FormMode } from '@/lib/snapshotForm'
import { ColourField, LocationFields } from './MetadataFields'
import type { FormValues } from './types'

const NO_MATERIAL = '__same__'

type Props = {
  mode: FormMode
  values: FormValues
  set: (patch: Partial<FormValues>) => void
  setFields: (patch: Partial<FormValues['fields']>) => void
  datasets: DatasetView[]
  materials: Material[]
  /** A draw from this batch (8.105): the quantity is the pieces taken out of it. */
  batch?: { size: number; remaining: number } | null
}

export function DetailsStep({ mode, values, set, setFields, datasets, materials, batch }: Props) {
  const { fields } = values
  const creating = mode === 'new' || mode === 'cut'

  return (
    <div className="space-y-5">
      {creating && datasets.length > 1 && (
        <Field label="Dataset" htmlFor="sf-dataset"
          hint="The study or project the piece belongs to; it decides who may see and moderate it.">
          <Select value={values.dataset} onValueChange={(dataset) => set({ dataset })}>
            <SelectTrigger id="sf-dataset" className="w-full">
              <SelectValue placeholder="Choose a dataset" />
            </SelectTrigger>
            <SelectContent>
              {datasets.map((d) => (
                <SelectItem key={d._id} value={d._id}>{d.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}
      {creating && datasets.length === 1 && (
        <p className="text-sm">
          <span className="text-muted-foreground">Dataset: </span>
          <span className="font-medium">{datasets[0].name}</span>
        </p>
      )}
      {creating && datasets.length === 0 && (
        <p role="alert" className="text-sm text-destructive">You contribute to no dataset, so you cannot record a piece yet.</p>
      )}

      {mode === 'new' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Original function" htmlFor="sf-function">
            <VocabSelect id="sf-function" labels={ORIGINAL_FUNCTION_LABELS} value={values.originalFunction}
              onChange={(originalFunction) => set({ originalFunction })} noneLabel="Choose" />
          </Field>
          <Field label="Material" htmlFor="sf-material">
            <Select value={values.material} onValueChange={(material) => set({ material })}>
              <SelectTrigger id="sf-material" className="w-full">
                <SelectValue placeholder="Choose" />
              </SelectTrigger>
              <SelectContent>
                {materials.filter((m) => !m.retired).map((m) => (
                  <SelectItem key={m._id} value={m._id}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
      )}

      {mode === 'cut' && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Original function" htmlFor="sf-function" className="sm:col-span-2"
            hint="The piece takes over origin, material, manufacture and function from its parents; state one only to override it, or when merged parents disagree.">
            <VocabSelect id="sf-function" labels={ORIGINAL_FUNCTION_LABELS} value={values.originalFunction}
              onChange={(originalFunction) => set({ originalFunction })} allowNone
              noneLabel="Same as the parents" />
          </Field>
          <Field label="Material" htmlFor="sf-material">
            <Select value={values.material || NO_MATERIAL}
              onValueChange={(material) => set({ material: material === NO_MATERIAL ? '' : material })}>
              <SelectTrigger id="sf-material" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_MATERIAL}>Same as the parents</SelectItem>
                {materials.filter((m) => !m.retired).map((m) => (
                  <SelectItem key={m._id} value={m._id}>{m.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" htmlFor="sf-name" className="sm:col-span-2">
          <Input id="sf-name" value={fields.name} onChange={(event) => setFields({ name: event.target.value })}
            placeholder={mode === 'correct' || mode === 'state' ? 'Name of this version' : 'Empty: the catalog number'} />
        </Field>

        {(mode === 'cut' || mode === 'state') && (
          <OptionalDateInput id="sf-effective"
            label={mode === 'cut' ? 'Cut on (empty: today)' : 'This state began on (empty: today)'}
            value={fields.effectiveOn} onChange={(effectiveOn) => setFields({ effectiveOn })} />
        )}

        <Field label={batch ? 'Pieces to draw' : 'Quantity'} htmlFor="sf-quantity"
          hint={batch
            ? `${batch.remaining} of ${batch.size} pieces remain in the batch. More than one makes a sub-batch.`
            : 'Identical items counted as one catalog entry. More than one makes a batch that pieces can be drawn from.'}>
          <Input id="sf-quantity" type="number" min={1} max={batch ? Math.max(1, batch.remaining) : undefined}
            step={1} inputMode="numeric" value={fields.quantity}
            onChange={(event) => setFields({ quantity: Math.max(1, parseInt(event.target.value, 10) || 1) })} />
        </Field>
        <div className="flex items-center gap-2 self-center">
          <Checkbox id="sf-fragment" checked={fields.fragment}
            onCheckedChange={(checked) => setFields({ fragment: checked === true })} />
          <Label htmlFor="sf-fragment">Fragment of a larger piece</Label>
        </div>

      </div>

      <details className="rounded-md border border-border p-3">
        <summary className="cursor-pointer text-sm font-medium">More: notes, colour, location</summary>
        <div className="mt-3 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            {mode === 'new' && (
              <Field label="Trade name" htmlFor="sf-trade" className="sm:col-span-2">
                <Input id="sf-trade" value={values.tradeName} maxLength={200}
                  onChange={(event) => set({ tradeName: event.target.value })} placeholder="Optional" />
              </Field>
            )}
            <ColourField fields={fields} setFields={setFields} />
            <Field label="Notes" htmlFor="sf-notes" className="sm:col-span-2">
              <Textarea id="sf-notes" rows={3} maxLength={5000} value={fields.notes}
                onChange={(event) => setFields({ notes: event.target.value })}
                placeholder="Markings, site observations, where it is stored" />
            </Field>
          </div>
          <LocationFields fields={fields} setFields={setFields} />
        </div>
      </details>

      {mode === 'new' && (
        <details className="rounded-md border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">Where it came from (optional)</summary>
          <div className="mt-3 space-y-3">
            <p className="text-xs text-muted-foreground">
              How the piece entered circulation. It can also be edited on the component page later.
            </p>
            <OriginFields idPrefix="sf-origin" value={values.origin ?? emptyOrigin()}
              onChange={(origin) => set({ origin })} />
          </div>
        </details>
      )}
    </div>
  )
}
