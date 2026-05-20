'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Loader2, Save, XCircle } from 'lucide-react'

import { ComponentLocation } from '@/generated/ComponentModel'
import type { CatalogComponent } from '@/generated/CatalogModels'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { OptionalDateInput } from '@/components/ui/optional-date-input'
import { Textarea } from '@/components/ui/textarea'
import { Checkbox } from '@/components/ui/checkbox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { hexComponentColor } from '@/lib/utils'
const COMPONENT_TYPES = [
  'panel',
  'beam',
  'column',
  'slab',
  'rubble',
  'brick',
  'pipe',
  'profile',
  'connector',
  'other',
] as const
const CONDITION_VALUES = [0, 1, 2, 3] as const
const MANUFACTURED_PRECISIONS = ['exact', 'month', 'year', 'unknown'] as const

const CONDITION_LABELS: Record<number, string> = {
  0: '0 — Destroyed / Retired',
  1: '1 — Poor',
  2: '2 — Average',
  3: '3 — Good',
}

const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// Sentinel string used by the condition/precision Selects to represent
// "no value / unknown". shadcn/ui Select does not accept empty-string
// SelectItem values.
const UNSET = '__unset__'

type FormState = {
  name: string
  type: string
  material: string
  dataset: string
  complexity: number
  fragment: boolean
  assembly: boolean
  colorR: number
  colorG: number
  colorB: number
  lat: number
  lon: number
  // Provenance / lineage fields. Empty string / null in form state means
  // "unset" and is sent to the backend as an explicit null in the PATCH
  // payload, which clears the field.
  condition: number | null
  manufactured_at: string        // stored as 'YYYY-MM-DD', serialized on submit
  manufactured_precision: string // one of MANUFACTURED_PRECISIONS or ''
  salvage_source: string
  salvaged_at: string            // stored as 'YYYY-MM-DD', serialized on submit
  parent_component: string
  notes: string
  quantity: number
}

function coerceNumber(value: string, fallback: number): number {
  const n = parseFloat(value)
  return Number.isFinite(n) ? n : fallback
}

function clampInt(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min
  return Math.max(min, Math.min(max, Math.round(value)))
}

function hexToRgb(hex: string): [number, number, number] | null {
  const m = hex.trim().replace(/^#/, '')
  if (m.length !== 6) return null
  const r = parseInt(m.slice(0, 2), 16)
  const g = parseInt(m.slice(2, 4), 16)
  const b = parseInt(m.slice(4, 6), 16)
  if ([r, g, b].some(v => Number.isNaN(v))) return null
  return [r, g, b]
}

// ISO-like string (possibly "YYYY-MM-DDTHH:mm:ssZ" or "YYYY-MM-DD") -> 'YYYY-MM-DD'.
// Returns '' when the input is not a usable date string.
function isoToDateInput(value: unknown): string {
  if (typeof value !== 'string' || value.trim() === '') return ''
  const trimmed = value.trim()
  // Already a YYYY-MM-DD prefix? Just take it.
  const m = trimmed.match(/^(\d{4}-\d{2}-\d{2})/)
  if (m) return m[1]
  const d = new Date(trimmed)
  if (Number.isNaN(d.getTime())) return ''
  return d.toISOString().slice(0, 10)
}

// 'YYYY-MM-DD' input value -> 'YYYY-MM-DDT00:00:00Z' for the backend. The
// time-of-day is conventional; provenance dates carry a `manufactured_precision`
// qualifier rather than a real wall-clock time.
function dateInputToIso(value: string): string {
  const trimmed = value.trim()
  if (trimmed === '') return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return `${trimmed}T00:00:00Z`
  }
  return trimmed
}

function initialStateFromCatalog(catalog: CatalogComponent): FormState {
  const { identity, snapshot } = catalog
  const colorArr = Array.isArray(snapshot.color) ? (snapshot.color as number[]) : [110, 110, 110]
  const loc = (snapshot.location as ComponentLocation | undefined) ?? { lat: 0, lon: 0 }
  const rawCondition = snapshot.condition
  const condition =
    typeof rawCondition === 'number' && CONDITION_VALUES.includes(rawCondition as typeof CONDITION_VALUES[number])
      ? (rawCondition as number)
      : null
  const rawPrecision = identity.manufactured_precision
  const precision =
    typeof rawPrecision === 'string' &&
    MANUFACTURED_PRECISIONS.includes(rawPrecision as typeof MANUFACTURED_PRECISIONS[number])
      ? rawPrecision
      : ''
  const parentIds = identity.parent_identities
  const parentId =
    Array.isArray(parentIds) && parentIds.length > 0 ? String(parentIds[0]) : ''
  return {
    name: typeof snapshot.name === 'string' ? snapshot.name : '',
    type: identity.type ?? '',
    material: identity.material ?? '',
    dataset: identity.dataset ?? '',
    complexity: typeof snapshot.complexity === 'number' ? snapshot.complexity : 0,
    fragment: Boolean(snapshot.fragment),
    assembly: Boolean(snapshot.assembly),
    colorR: clampInt(colorArr[0] ?? 110, 0, 255),
    colorG: clampInt(colorArr[1] ?? 110, 0, 255),
    colorB: clampInt(colorArr[2] ?? 110, 0, 255),
    lat: typeof loc?.lat === 'number' ? loc.lat : 0,
    lon: typeof loc?.lon === 'number' ? loc.lon : 0,
    condition,
    manufactured_at: isoToDateInput(identity.manufactured_at),
    manufactured_precision: precision,
    salvage_source: typeof identity.salvage_source === 'string' ? identity.salvage_source : '',
    salvaged_at: isoToDateInput(identity.salvaged_at),
    parent_component: parentId,
    notes: typeof snapshot.notes === 'string' ? snapshot.notes : '',
    quantity:
      typeof snapshot.quantity === 'number' && snapshot.quantity >= 1
        ? Math.floor(snapshot.quantity)
        : 1,
  }
}

export default function ComponentEditForm({
  catalog,
}: {
  catalog: CatalogComponent
}) {
  const router = useRouter()
  const identityId = catalog.identity._id ?? ''
  const initial = useMemo(() => initialStateFromCatalog(catalog), [catalog])
  const [form, setForm] = useState<FormState>(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [materialSuggestions, setMaterialSuggestions] = useState<string[]>([])
  const [datasetSuggestions, setDatasetSuggestions] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const [mRes, dRes] = await Promise.all([
          fetch('/api/backend/identities/meta/materials', { credentials: 'include' }).then(r =>
            r.ok ? r.json() : [],
          ),
          fetch('/api/backend/identities/meta/datasets', { credentials: 'include' }).then(r =>
            r.ok ? r.json() : [],
          ),
        ])
        if (cancelled) return
        if (Array.isArray(mRes)) setMaterialSuggestions(mRes.filter(Boolean))
        if (Array.isArray(dRes)) setDatasetSuggestions(dRes.filter(Boolean))
      } catch {
        // non-fatal; suggestions are optional
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const dirty = useMemo(() => {
    return (Object.keys(form) as (keyof FormState)[]).some(
      k => form[k] !== initial[k]
    )
  }, [form, initial])

  const hexColor = hexComponentColor([form.colorR, form.colorG, form.colorB])

  const setField = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  const handleReset = () => {
    setForm(initial)
    setError(null)
    setSuccess(null)
  }

  const parseApiError = async (res: Response): Promise<string> => {
    let detail = `Failed with status ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) {
        detail =
          typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail)
      }
    } catch {
      // ignore
    }
    return detail
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)

    const snapshotPatch: Record<string, unknown> = {}
    const identityPatch: Record<string, unknown> = {}

    if (form.name.trim() !== (initial.name ?? '').trim()) {
      snapshotPatch.name = form.name.trim()
    }
    if (form.fragment !== initial.fragment) snapshotPatch.fragment = form.fragment
    if (form.assembly !== initial.assembly) snapshotPatch.assembly = form.assembly
    if (
      form.colorR !== initial.colorR ||
      form.colorG !== initial.colorG ||
      form.colorB !== initial.colorB
    ) {
      snapshotPatch.color = [
        clampInt(form.colorR, 0, 255),
        clampInt(form.colorG, 0, 255),
        clampInt(form.colorB, 0, 255),
      ]
    }
    if (form.lat !== initial.lat || form.lon !== initial.lon) {
      snapshotPatch.location = { lat: form.lat, lon: form.lon }
    }
    if (form.condition !== initial.condition) {
      snapshotPatch.condition = form.condition
    }
    if (form.notes.trim() !== initial.notes.trim()) {
      const next = form.notes.trim()
      snapshotPatch.notes = next === '' ? null : next
    }
    if (form.quantity !== initial.quantity) {
      snapshotPatch.quantity = Math.max(1, Math.floor(form.quantity))
    }

    if (form.type !== initial.type) identityPatch.type = form.type
    if (form.material.trim() !== initial.material.trim()) {
      identityPatch.material = form.material.trim()
    }
    if (form.dataset.trim() !== initial.dataset.trim()) {
      identityPatch.dataset = form.dataset.trim()
    }
    if (form.manufactured_at !== initial.manufactured_at) {
      identityPatch.manufactured_at =
        form.manufactured_at.trim() === ''
          ? null
          : dateInputToIso(form.manufactured_at)
    }
    if (form.manufactured_precision !== initial.manufactured_precision) {
      identityPatch.manufactured_precision =
        form.manufactured_precision === '' ? null : form.manufactured_precision
    }
    if (form.salvaged_at !== initial.salvaged_at) {
      identityPatch.salvaged_at =
        form.salvaged_at.trim() === '' ? null : dateInputToIso(form.salvaged_at)
    }
    if (form.salvage_source.trim() !== initial.salvage_source.trim()) {
      const next = form.salvage_source.trim()
      identityPatch.salvage_source = next === '' ? null : next
    }
    if (form.parent_component.trim() !== initial.parent_component.trim()) {
      const next = form.parent_component.trim()
      if (next === '') {
        identityPatch.parent_identities = null
      } else if (!UUID_REGEX.test(next)) {
        setError('Parent identity must be a valid UUID.')
        return
      } else if (next.toLowerCase() === identityId.toLowerCase()) {
        setError('Parent identity cannot reference itself.')
        return
      } else {
        identityPatch.parent_identities = [next.toLowerCase()]
      }
    }

    if (
      Object.keys(snapshotPatch).length === 0 &&
      Object.keys(identityPatch).length === 0
    ) {
      setError('No changes to save.')
      return
    }

    if (typeof snapshotPatch.name === 'string' && snapshotPatch.name === '') {
      setError('Name cannot be empty.')
      return
    }
    if (typeof identityPatch.material === 'string' && identityPatch.material === '') {
      setError('Material cannot be empty.')
      return
    }
    if (typeof identityPatch.dataset === 'string' && identityPatch.dataset === '') {
      setError('Dataset cannot be empty.')
      return
    }
    if (
      identityPatch.type &&
      !COMPONENT_TYPES.includes(identityPatch.type as typeof COMPONENT_TYPES[number])
    ) {
      setError(`Type must be one of: ${COMPONENT_TYPES.join(', ')}.`)
      return
    }

    try {
      setSaving(true)
      const base = `/api/backend/identities/${encodeURIComponent(identityId)}`
      const opts = {
        method: 'PATCH' as const,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include' as const,
      }

      if (Object.keys(snapshotPatch).length > 0) {
        const res = await fetch(`${base}/current-snapshot`, {
          ...opts,
          body: JSON.stringify(snapshotPatch),
        })
        if (!res.ok) {
          throw new Error(`Snapshot update: ${await parseApiError(res)}`)
        }
      }

      if (Object.keys(identityPatch).length > 0) {
        const res = await fetch(base, {
          ...opts,
          body: JSON.stringify(identityPatch),
        })
        if (!res.ok) {
          throw new Error(`Identity update: ${await parseApiError(res)}`)
        }
      }

      setSuccess('Component metadata updated successfully.')
      router.refresh()
      setTimeout(() => {
        router.push(`/components/${identityId}`)
      }, 600)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error'
      setError(`Failed to update component: ${message}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Identification</CardTitle>
          <CardDescription>
            Human-readable name, type, and classification.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={form.name}
              onChange={e => setField('name', e.target.value)}
              placeholder="Unnamed Component"
              maxLength={200}
              required
            />
          </div>

          <div>
            <Label htmlFor="type">Type</Label>
            <Select
              value={form.type}
              onValueChange={v => setField('type', v)}
            >
              <SelectTrigger id="type">
                <SelectValue placeholder="Select a type" />
              </SelectTrigger>
              <SelectContent>
                {COMPONENT_TYPES.map(t => (
                  <SelectItem key={t} value={t}>{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="complexity">Complexity</Label>
            <Input
              id="complexity"
              value={String(form.complexity)}
              readOnly
              disabled
              className="bg-muted text-muted-foreground"
              title="Derived from geometry; create a new snapshot to change"
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Read-only (geometry-derived).
            </p>
          </div>

          <div>
            <Label htmlFor="material">Material</Label>
            <Input
              id="material"
              value={form.material}
              onChange={e => setField('material', e.target.value)}
              placeholder="e.g. wood, concrete"
              list="material-suggestions"
              maxLength={100}
              required
            />
            <datalist id="material-suggestions">
              {materialSuggestions.map(m => (
                <option key={m} value={m} />
              ))}
            </datalist>
          </div>

          <div>
            <Label htmlFor="dataset">Dataset</Label>
            <Input
              id="dataset"
              value={form.dataset}
              onChange={e => setField('dataset', e.target.value)}
              placeholder="e.g. demo, batch-2025-04"
              list="dataset-suggestions"
              maxLength={200}
              required
            />
            <datalist id="dataset-suggestions">
              {datasetSuggestions.map(d => (
                <option key={d} value={d} />
              ))}
            </datalist>
          </div>

          <div>
            <Label htmlFor="quantity">Quantity</Label>
            <Input
              id="quantity"
              type="number"
              min={1}
              step={1}
              value={form.quantity}
              onChange={e =>
                setField('quantity', Math.max(1, parseInt(e.target.value, 10) || 1))
              }
            />
          </div>

          <div className="sm:col-span-2">
            <Label htmlFor="notes">Notes</Label>
            <Textarea
              id="notes"
              value={form.notes}
              onChange={e => setField('notes', e.target.value)}
              rows={3}
              maxLength={5000}
              placeholder="Optional notes for this snapshot"
            />
          </div>

          {typeof catalog.snapshot.added_by_username === 'string' &&
            catalog.snapshot.added_by_username.trim() !== '' && (
              <div className="sm:col-span-2 text-sm text-muted-foreground">
                Added to catalog by{' '}
                <span className="font-medium text-foreground">
                  {catalog.snapshot.added_by_username}
                </span>
              </div>
            )}

          <div className="flex items-center gap-6 sm:col-span-2">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={form.fragment}
                onCheckedChange={v => setField('fragment', Boolean(v))}
              />
              Fragment
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={form.assembly}
                onCheckedChange={v => setField('assembly', Boolean(v))}
              />
              Assembly
            </label>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>
            RGB color used for previews and visualization.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-[auto_1fr]">
          <div className="flex flex-col items-center gap-2">
            <input
              aria-label="Color picker"
              type="color"
              value={hexColor}
              onChange={e => {
                const rgb = hexToRgb(e.target.value)
                if (rgb) {
                  setField('colorR', rgb[0])
                  setField('colorG', rgb[1])
                  setField('colorB', rgb[2])
                }
              }}
              className="h-16 w-16 cursor-pointer rounded-md border border-border bg-transparent p-1"
            />
            <span className="font-mono text-xs text-muted-foreground">{hexColor}</span>
          </div>

          <div className="grid grid-cols-3 gap-3">
            {(['colorR', 'colorG', 'colorB'] as const).map((k, idx) => {
              const label = ['R', 'G', 'B'][idx]
              return (
                <div key={k}>
                  <Label htmlFor={k}>{label}</Label>
                  <Input
                    id={k}
                    type="number"
                    min={0}
                    max={255}
                    step={1}
                    value={form[k]}
                    onChange={e => setField(k, clampInt(coerceNumber(e.target.value, 0), 0, 255))}
                  />
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Location</CardTitle>
          <CardDescription>
            Geographic coordinates associated with the component.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="lat">Latitude</Label>
            <Input
              id="lat"
              type="number"
              step="any"
              min={-90}
              max={90}
              value={form.lat}
              onChange={e => setField('lat', coerceNumber(e.target.value, 0))}
            />
          </div>
          <div>
            <Label htmlFor="lon">Longitude</Label>
            <Input
              id="lon"
              type="number"
              step="any"
              min={-180}
              max={180}
              value={form.lon}
              onChange={e => setField('lon', coerceNumber(e.target.value, 0))}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Provenance &amp; Lineage</CardTitle>
          <CardDescription>
            Optional history fields: condition grade, manufacturing and
            salvage dates, salvage source, and the parent component this
            piece was split from. Set a field to &ldquo;Unknown&rdquo; or
            empty to clear it on save.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div>
            <Label htmlFor="condition">Condition</Label>
            <Select
              value={form.condition === null ? UNSET : String(form.condition)}
              onValueChange={v =>
                setField('condition', v === UNSET ? null : Number(v))
              }
            >
              <SelectTrigger id="condition">
                <SelectValue placeholder="Select condition" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={UNSET}>Unknown</SelectItem>
                {CONDITION_VALUES.map(c => (
                  <SelectItem key={c} value={String(c)}>
                    {CONDITION_LABELS[c]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label htmlFor="manufactured_precision">Manufactured precision</Label>
            <Select
              value={form.manufactured_precision === '' ? UNSET : form.manufactured_precision}
              onValueChange={v =>
                setField('manufactured_precision', v === UNSET ? '' : v)
              }
            >
              <SelectTrigger id="manufactured_precision">
                <SelectValue placeholder="Select precision" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={UNSET}>Unknown</SelectItem>
                {MANUFACTURED_PRECISIONS.map(p => (
                  <SelectItem key={p} value={p}>{p}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <OptionalDateInput
            id="manufactured_at"
            label="Manufactured at"
            value={form.manufactured_at}
            onChange={v => setField('manufactured_at', v)}
          />

          <OptionalDateInput
            id="salvaged_at"
            label="Salvaged at"
            value={form.salvaged_at}
            onChange={v => setField('salvaged_at', v)}
          />

          <div className="sm:col-span-2">
            <Label htmlFor="salvage_source">Salvage source</Label>
            <Input
              id="salvage_source"
              value={form.salvage_source}
              onChange={e => setField('salvage_source', e.target.value)}
              placeholder="e.g. Old warehouse, Demolition site X, Building address"
              maxLength={500}
            />
          </div>

          <div className="sm:col-span-2">
            <Label htmlFor="parent_component">Parent component (UUID)</Label>
            <Input
              id="parent_component"
              value={form.parent_component}
              onChange={e => setField('parent_component', e.target.value)}
              placeholder="e.g. 6f1a4c1e-8b2d-4e3a-9c5f-1234567890ab"
              list="parent-component-suggestions"
              spellCheck={false}
              autoComplete="off"
              className="font-mono text-xs"
            />
            {form.parent_component.trim() !== '' &&
              !UUID_REGEX.test(form.parent_component.trim()) && (
                <p className="mt-1 text-xs text-destructive">
                  Not a valid UUID.
                </p>
              )}
            {form.parent_component.trim() !== '' &&
              form.parent_component.trim().toLowerCase() ===
                identityId.toLowerCase() && (
                <p className="mt-1 text-xs text-destructive">
                  A component cannot be its own parent.
                </p>
              )}
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
          <XCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="rounded-md border border-green-500/40 bg-green-500/10 p-3 text-sm text-green-700 dark:text-green-300">
          {success}
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href={`/components/${identityId}`}>
          <Button type="button" variant="ghost">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to details
          </Button>
        </Link>
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleReset}
            disabled={saving || !dirty}
          >
            Reset
          </Button>
          <Button type="submit" disabled={saving || !dirty}>
            {saving ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save changes
              </>
            )}
          </Button>
        </div>
      </div>
    </form>
  )
}
