'use client'

/**
 * Step "Size": an authored box from length x width x height (spec 7.6;
 * scans replace it later). A correction keeps the stored geometry unless a
 * size is entered again; a new state always needs one (only a changed shape
 * is a new state, decision 7.5).
 */
import { Field } from '@/components/lineage/fields'
import { Input } from '@/components/ui/input'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { boxAxisHint, sanitizeDimensionInput, type FormMode } from '@/lib/snapshotForm'
import type { FormValues } from './types'

const LABELS = ['Length', 'Width', 'Height'] as const

export function SizeStep({
  mode,
  values,
  set,
  column,
  currentSize,
  batch,
}: {
  mode: FormMode
  values: FormValues
  set: (patch: Partial<FormValues>) => void
  /** A column stands: its longest side is its height. */
  column: boolean
  /** Correct / state: the size of the version on screen, as typed fields. */
  currentSize: [string, string, string] | null
  /** A draw from a batch: its proxy is the default (8.105). */
  batch?: boolean
}) {
  const keeping = (mode === 'correct' || batch === true) && !values.sizeEntered
  const same = mode === 'state' && currentSize
    && values.dims.every((v, i) => Number(v.replace(',', '.')) === Number(currentSize[i]))

  return (
    <div className="space-y-4">
      {(mode === 'correct' || batch) && (
        <div className="space-y-2 rounded-md border border-border p-3">
          <div className="flex items-center gap-2">
            <Checkbox id="sf-size-again" checked={values.sizeEntered}
              onCheckedChange={(checked) => set({ sizeEntered: checked === true })} />
            <Label htmlFor="sf-size-again">
              {batch ? 'This piece has a size of its own: enter it' : 'The size was wrong: enter it again'}
            </Label>
          </div>
          <p className="text-xs text-muted-foreground">
            {batch
              ? keeping
                ? "The pieces take the batch's proxy: they are identical."
                : "An authored box for these pieces instead of the batch's proxy."
              : keeping
                ? `The geometry of this version is kept${currentSize ? ` (${currentSize.join(' x ')} mm)` : ''}.`
                : 'Evidence positioned on this version keeps its points; the form lists it next.'}
          </p>
        </div>
      )}

      {!keeping && (
        <Field label="Size (mm)" hint={`An authored box; ${boxAxisHint(column)}.`}>
          <div className="grid grid-cols-3 gap-2">
            {LABELS.map((label, i) => (
              <div key={label} className="space-y-1">
                <Label htmlFor={`sf-dim-${i}`} className="text-xs text-muted-foreground">{label}</Label>
                <Input id={`sf-dim-${i}`} inputMode="decimal" autoComplete="off" placeholder="mm"
                  value={values.dims[i]}
                  onChange={(event) => {
                    const next = [...values.dims] as FormValues['dims']
                    next[i] = sanitizeDimensionInput(event.target.value)
                    set({ dims: next })
                  }} />
              </div>
            ))}
          </div>
        </Field>
      )}

      {same && (
        <p role="status" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100">
          This is the size of the current state. A new state is for a changed shape; damage or weathering
          without a change of shape is recorded as evidence (Add evidence, visual inspection).
        </p>
      )}
    </div>
  )
}
