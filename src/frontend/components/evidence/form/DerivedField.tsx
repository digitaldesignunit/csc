'use client'

/**
 * An optional derived result of one record (decision 8.41), for example a
 * strength class read from the German annex for a rebound median. The
 * model kinds, their labels and what they need (a note, a reference) are
 * the registry's; the server builds a core's in-situ strength itself.
 */
import { Field, NativeSelect } from '@/components/evidence/controls'
import type { DerivedState } from '@/components/evidence/form/state'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { MethodInfo, QuantityInfo } from '@/lib/evidence/api'
import { quantityLabel } from '@/lib/evidence/format'

export default function DerivedField({
  id,
  method,
  quantities,
  value,
  onChange,
  errors,
}: {
  id: string
  method: MethodInfo
  quantities: QuantityInfo[]
  value: DerivedState
  onChange: (next: DerivedState) => void
  errors?: string[]
}) {
  const models = method.derived_models.filter((m) => !m.server_built)
  if (models.length === 0) return null
  const model = models.find((m) => m.kind === value.model)
  const quantity = model ? quantities.find((q) => q.name === model.quantity) : undefined
  const classes = quantity?.values ?? null

  return (
    <fieldset className="space-y-3 rounded-md border border-dashed border-border p-3">
      <legend className="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Derived result (optional)
      </legend>
      <Field
        id={`${id}-model`}
        label="How it was derived"
        help={models.map((m) => `${m.label}: ${m.description}`).join('\n\n')}
        errors={errors}
      >
        <NativeSelect
          id={`${id}-model`}
          value={value.model}
          onChange={(next) => onChange({ ...value, model: next })}
          placeholder="None"
          options={models.map((m) => ({ value: m.kind, label: m.label }))}
        />
      </Field>
      {model && (
        <>
          {model.description && (
            <p className="text-xs text-muted-foreground">{model.description}</p>
          )}
          <Field id={`${id}-value`} label={quantityLabel(model.quantity)} required>
            {classes ? (
              <NativeSelect
                id={`${id}-value`}
                value={value.value}
                onChange={(next) => onChange({ ...value, value: next })}
                options={classes.map((c) => ({ value: c, label: c }))}
              />
            ) : (
              <Input
                id={`${id}-value`}
                value={value.value}
                inputMode={quantity?.kind === 'scalar' ? 'decimal' : undefined}
                onChange={(event) => onChange({ ...value, value: event.target.value })}
              />
            )}
          </Field>
          {(model.needs_note || value.note) && (
            <Field
              id={`${id}-note`}
              label="Note"
              required={model.needs_note}
            >
              <Textarea
                id={`${id}-note`}
                rows={2}
                value={value.note}
                onChange={(event) => onChange({ ...value, note: event.target.value })}
              />
            </Field>
          )}
          {(model.needs_reference || value.reference) && (
            <Field
              id={`${id}-reference`}
              label="Reference"
              required={model.needs_reference}
            >
              <Input
                id={`${id}-reference`}
                value={value.reference}
                onChange={(event) => onChange({ ...value, reference: event.target.value })}
              />
            </Field>
          )}
        </>
      )}
    </fieldset>
  )
}
