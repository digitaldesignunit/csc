'use client'

/**
 * Edit a component's provenance metadata (`PATCH /identities/{id}`; spec
 * section 3.1.1, 3.1.2, I17, I25; decisions 8.31 -- 8.38). A child shows
 * per inheritance unit whether it follows its parents: editing a unit makes
 * it the child's own, ticking "from the parents" again takes it back. Only
 * changed fields are sent; the backend checks every rule again.
 */
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'

import type {
  CircularityClass,
  ComponentIdentity,
  Origin,
} from '@/generated/CatalogModels'
import {
  INHERIT_UNIT_LABELS,
  ORIGINAL_FUNCTION_LABELS,
  PRECISION_LABELS,
  type InheritUnit,
  type OriginalFunction,
} from '@/generated/Vocab'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { backendJson } from '@/lib/backend'
import {
  assessedClass,
  cleanOrigin,
  emptyOrigin,
  INHERIT_UNITS,
  isInherited,
  sameJson,
  useMaterials,
} from '@/lib/lineage'
import { useMe } from '@/lib/me'
import {
  CircularityClassField,
  DateWithPrecision,
  Field,
  OriginFields,
  VocabSelect,
} from './fields'

type Precision = keyof typeof PRECISION_LABELS

type Draft = {
  original_function: OriginalFunction
  material: string
  classMode: 'derived' | 'assigned'
  material_class: string
  trade_name: string
  manufacturer: string
  manufactured_at: string | null
  manufactured_precision: Precision
  material_separability: CircularityClass | null
  connection_features: string
  origin: Origin
}

function draftOf(identity: ComponentIdentity): Draft {
  return {
    original_function: identity.original_function,
    material: identity.material,
    classMode: identity.material_class_source === 'assigned' ? 'assigned' : 'derived',
    material_class: identity.material_class ?? '',
    trade_name: identity.trade_name ?? '',
    manufacturer: identity.manufacturer ?? '',
    manufactured_at: identity.manufactured_at ?? null,
    manufactured_precision: (identity.manufactured_precision ?? 'unknown') as Precision,
    material_separability: identity.material_separability ?? null,
    connection_features: identity.connection_features ?? '',
    origin: identity.origin ?? emptyOrigin(),
  }
}

function text(value: string): string | null {
  return value.trim() ? value.trim() : null
}

/** The fields of one unit as the PATCH sends them. */
function unitPatch(
  unit: InheritUnit,
  draft: Draft,
  identity: ComponentIdentity,
  userId: string | undefined,
): Record<string, unknown> {
  switch (unit) {
    case 'origin':
      return { origin: cleanOrigin(draft.origin) }
    case 'manufactured_at':
      return {
        manufactured_at: draft.manufactured_at,
        manufactured_precision: draft.manufactured_at ? draft.manufactured_precision : 'unknown',
      }
    case 'material':
      if (draft.classMode === 'assigned') {
        return { material: draft.material, material_class: draft.material_class.trim() }
      }
      // null returns an assigned class to the material's default (I25)
      return identity.material_class_source === 'assigned'
        ? { material: draft.material, material_class: null }
        : { material: draft.material }
    case 'trade_name':
      return { trade_name: text(draft.trade_name) }
    case 'manufacturer':
      return { manufacturer: text(draft.manufacturer) }
    case 'material_separability':
      return {
        material_separability: assessedClass(
          draft.material_separability, identity.material_separability, userId),
      }
    case 'original_function':
      return { original_function: draft.original_function }
  }
}

function storedUnit(unit: InheritUnit, identity: ComponentIdentity): Record<string, unknown> {
  return unitPatch(unit, draftOf(identity), identity, undefined)
}

export function buildPatch(
  identity: ComponentIdentity,
  draft: Draft,
  inherit: Record<InheritUnit, boolean>,
  userId: string | undefined,
): Record<string, unknown> {
  const patch: Record<string, unknown> = {}
  let reinherit = false
  for (const unit of INHERIT_UNITS) {
    const was = isInherited(identity, unit)
    const now = inherit[unit]
    if (now) {
      reinherit ||= !was
      continue
    }
    const fields = unitPatch(unit, draft, identity, userId)
    // a unit the child stops inheriting is sent whole: that detaches it
    if (was) {
      Object.assign(patch, fields)
      continue
    }
    const stored = storedUnit(unit, identity)
    if (unit === 'material') {
      const classChanged = draft.classMode !== (identity.material_class_source === 'assigned' ? 'assigned' : 'derived')
        || (draft.classMode === 'assigned' && draft.material_class.trim() !== identity.material_class)
      if (draft.material !== identity.material || classChanged) Object.assign(patch, fields)
      continue
    }
    if (!sameJson(fields, stored)) Object.assign(patch, fields)
  }
  if (reinherit) {
    patch.inherited_fields = INHERIT_UNITS.filter((unit) => inherit[unit])
  }
  const features = text(draft.connection_features)
  if (features !== (identity.connection_features ?? null)) {
    patch.connection_features = features
  }
  return patch
}

function UnitSection({ unit, title, hasParents, inherited, onInherit, children }: {
  unit: InheritUnit
  title?: string
  hasParents: boolean
  inherited: boolean
  onInherit: (value: boolean) => void
  children: ReactNode
}) {
  return (
    <section className="space-y-3 rounded-lg border border-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title ?? INHERIT_UNIT_LABELS[unit]}</h3>
        {hasParents && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Checkbox checked={inherited} onCheckedChange={(checked) => onInherit(checked === true)} />
            From the parents
          </label>
        )}
      </div>
      {children}
    </section>
  )
}

type Props = {
  identity: ComponentIdentity
  open: boolean
  onOpenChange: (open: boolean) => void
}

export default function ProvenanceEditDialog({ identity, open, onOpenChange }: Props) {
  const router = useRouter()
  const { me } = useMe()
  const materials = useMaterials(true)
  const [draft, setDraft] = useState<Draft>(() => draftOf(identity))
  const initialInherit = useMemo(
    () => Object.fromEntries(INHERIT_UNITS.map((u) => [u, isInherited(identity, u)])) as Record<InheritUnit, boolean>,
    [identity],
  )
  const [inherit, setInherit] = useState(initialInherit)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const hasParents = (identity.parent_identities ?? []).length > 0

  useEffect(() => {
    if (open) {
      setDraft(draftOf(identity))
      setInherit(initialInherit)
      setError(null)
    }
  }, [open, identity, initialInherit])

  const set = (patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch }))
  const offered = materials.filter((m) => !m.retired || m._id === identity.material)
  const material = materials.find((m) => m._id === draft.material)
  const locked = (unit: InheritUnit) => hasParents && inherit[unit]

  const save = async () => {
    const patch = buildPatch(identity, draft, inherit, me?._id)
    if (Object.keys(patch).length === 0) {
      onOpenChange(false)
      return
    }
    setBusy(true)
    setError(null)
    try {
      await backendJson(`/identities/${identity._id}`, { method: 'PATCH', body: patch })
      toast.success('Provenance saved')
      onOpenChange(false)
      router.refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Saving failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!busy) onOpenChange(next) }}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Edit provenance</DialogTitle>
          <DialogDescription>
            {hasParents
              ? "Ticked units follow the parents and change with them. Untick one to make it this component's own."
              : 'Pieces cut from this component take these values over until they state their own.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <UnitSection unit="original_function" hasParents={hasParents}
            inherited={inherit.original_function}
            onInherit={(v) => setInherit((s) => ({ ...s, original_function: v }))}>
            <VocabSelect
              id="edit-original-function"
              labels={ORIGINAL_FUNCTION_LABELS}
              value={draft.original_function}
              onChange={(value) => value && set({ original_function: value })}
              disabled={locked('original_function')}
            />
          </UnitSection>

          <UnitSection unit="material" hasParents={hasParents} inherited={inherit.material}
            onInherit={(v) => setInherit((s) => ({ ...s, material: v }))}>
            <fieldset disabled={locked('material')} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Field label="Material" htmlFor="edit-material">
                <Select value={draft.material} onValueChange={(value) => set({ material: value })}
                  disabled={locked('material')}>
                  <SelectTrigger id="edit-material" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {offered.map((m) => (
                      <SelectItem key={m._id} value={m._id}>
                        {m.label}{m.retired ? ' (retired)' : ''}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Waste class (EU List of Waste)" htmlFor="edit-class-mode">
                <Select value={draft.classMode}
                  onValueChange={(value) => set({ classMode: value as Draft['classMode'] })}
                  disabled={locked('material')}>
                  <SelectTrigger id="edit-class-mode" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="derived">
                      From the material{material ? ` (${material.default_class})` : ''}
                    </SelectItem>
                    <SelectItem value="assigned">Set by hand</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              {draft.classMode === 'assigned' && (
                <Field label="Class" htmlFor="edit-class" hint="Six digits, e.g. 17 01 07; a hazardous entry ends with *."
                  className="sm:col-span-2">
                  <Input id="edit-class" value={draft.material_class}
                    onChange={(event) => set({ material_class: event.target.value })} />
                </Field>
              )}
            </fieldset>
          </UnitSection>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <UnitSection unit="trade_name" hasParents={hasParents} inherited={inherit.trade_name}
              onInherit={(v) => setInherit((s) => ({ ...s, trade_name: v }))}>
              <Input aria-label="Trade name" value={draft.trade_name} disabled={locked('trade_name')}
                onChange={(event) => set({ trade_name: event.target.value })} />
            </UnitSection>
            <UnitSection unit="manufacturer" hasParents={hasParents} inherited={inherit.manufacturer}
              onInherit={(v) => setInherit((s) => ({ ...s, manufacturer: v }))}>
              <Input aria-label="Manufacturer" value={draft.manufacturer} disabled={locked('manufacturer')}
                onChange={(event) => set({ manufacturer: event.target.value })} />
            </UnitSection>
          </div>

          <UnitSection unit="manufactured_at" hasParents={hasParents} inherited={inherit.manufactured_at}
            onInherit={(v) => setInherit((s) => ({ ...s, manufactured_at: v }))}>
            <DateWithPrecision
              id="edit-manufactured"
              label="Manufactured on"
              at={draft.manufactured_at}
              precision={draft.manufactured_precision}
              onChange={(at, precision) => set({ manufactured_at: at, manufactured_precision: precision })}
              disabled={locked('manufactured_at')}
            />
          </UnitSection>

          <UnitSection unit="material_separability" hasParents={hasParents}
            inherited={inherit.material_separability}
            onInherit={(v) => setInherit((s) => ({ ...s, material_separability: v }))}>
            <CircularityClassField
              id="edit-separability"
              label="DGNB class"
              hint="How well its materials come apart from each other."
              value={draft.material_separability}
              onChange={(material_separability) => set({ material_separability })}
              disabled={locked('material_separability')}
            />
          </UnitSection>

          <UnitSection unit="origin" hasParents={hasParents} inherited={inherit.origin}
            onInherit={(v) => setInherit((s) => ({ ...s, origin: v }))}>
            <OriginFields idPrefix="edit-origin" value={draft.origin}
              onChange={(origin) => set({ origin })} disabled={locked('origin')} />
          </UnitSection>

          <section className="space-y-2 rounded-lg border border-border p-3">
            <h3 className="text-sm font-semibold">Connection features</h3>
            <p className="text-xs text-muted-foreground">
              Anchors, dowels, plates or holes on this piece. Its own: never taken over by pieces cut from it.
            </p>
            <Textarea aria-label="Connection features" rows={2} value={draft.connection_features}
              onChange={(event) => set({ connection_features: event.target.value })} />
          </section>

          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
          <Button onClick={() => void save()} disabled={busy}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
