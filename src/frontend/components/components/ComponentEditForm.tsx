'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { ArrowLeft, Loader2, Save, XCircle } from 'lucide-react'

import { ExtendedComponentModel, ComponentLocation } from '@/generated/ComponentModel'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
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
const COMPLEXITY_LEVELS = [0, 1, 2, 3] as const

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

function initialStateFromComponent(c: ExtendedComponentModel): FormState {
  const colorArr = Array.isArray(c.color) ? c.color as number[] : [110, 110, 110]
  const loc = (c.location as ComponentLocation | undefined) ?? { lat: 0, lon: 0 }
  return {
    name: typeof c.name === 'string' ? c.name : '',
    type: c.type ?? '',
    material: c.material ?? '',
    dataset: c.dataset ?? '',
    complexity: typeof c.complexity === 'number' ? c.complexity : 0,
    fragment: Boolean(c.fragment),
    assembly: Boolean(c.assembly),
    colorR: clampInt(colorArr[0] ?? 110, 0, 255),
    colorG: clampInt(colorArr[1] ?? 110, 0, 255),
    colorB: clampInt(colorArr[2] ?? 110, 0, 255),
    lat: typeof loc?.lat === 'number' ? loc.lat : 0,
    lon: typeof loc?.lon === 'number' ? loc.lon : 0,
  }
}

export default function ComponentEditForm({
  component_data,
}: {
  component_data: ExtendedComponentModel
}) {
  const router = useRouter()
  const initial = useMemo(() => initialStateFromComponent(component_data), [component_data])
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
          fetch('/api/backend/materials').then(r => (r.ok ? r.json() : [])),
          fetch('/api/backend/datasets').then(r => (r.ok ? r.json() : [])),
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)

    // Build a minimal patch: only include fields that actually changed
    const patch: Record<string, unknown> = {}
    if (form.name.trim() !== (initial.name ?? '').trim()) patch.name = form.name.trim()
    if (form.type !== initial.type) patch.type = form.type
    if (form.material.trim() !== initial.material.trim()) patch.material = form.material.trim()
    if (form.dataset.trim() !== initial.dataset.trim()) patch.dataset = form.dataset.trim()
    if (form.complexity !== initial.complexity) patch.complexity = form.complexity
    if (form.fragment !== initial.fragment) patch.fragment = form.fragment
    if (form.assembly !== initial.assembly) patch.assembly = form.assembly
    if (
      form.colorR !== initial.colorR ||
      form.colorG !== initial.colorG ||
      form.colorB !== initial.colorB
    ) {
      patch.color = [
        clampInt(form.colorR, 0, 255),
        clampInt(form.colorG, 0, 255),
        clampInt(form.colorB, 0, 255),
      ]
    }
    if (form.lat !== initial.lat || form.lon !== initial.lon) {
      patch.location = { lat: form.lat, lon: form.lon }
    }

    if (Object.keys(patch).length === 0) {
      setError('No changes to save.')
      return
    }

    // Client-side basic validation
    if (typeof patch.name === 'string' && patch.name === '') {
      setError('Name cannot be empty.')
      return
    }
    if (typeof patch.material === 'string' && patch.material === '') {
      setError('Material cannot be empty.')
      return
    }
    if (typeof patch.dataset === 'string' && patch.dataset === '') {
      setError('Dataset cannot be empty.')
      return
    }
    if (patch.type && !COMPONENT_TYPES.includes(patch.type as typeof COMPONENT_TYPES[number])) {
      setError(`Type must be one of: ${COMPONENT_TYPES.join(', ')}.`)
      return
    }

    try {
      setSaving(true)
      const res = await fetch(
        `/api/backend/components/${encodeURIComponent(component_data._id ?? '')}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch),
        }
      )
      if (!res.ok) {
        let detail = `Failed with status ${res.status}`
        try {
          const body = await res.json()
          if (body?.detail) {
            detail = typeof body.detail === 'string'
              ? body.detail
              : JSON.stringify(body.detail)
          }
        } catch {
          // ignore
        }
        throw new Error(detail)
      }
      setSuccess('Component metadata updated successfully.')
      router.refresh()
      setTimeout(() => {
        router.push(`/components/${component_data._id}`)
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
            <Select
              value={String(form.complexity)}
              onValueChange={v => setField('complexity', Number(v))}
            >
              <SelectTrigger id="complexity">
                <SelectValue placeholder="Select complexity" />
              </SelectTrigger>
              <SelectContent>
                {COMPLEXITY_LEVELS.map(c => (
                  <SelectItem key={c} value={String(c)}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
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
        <Link href={`/components/${component_data._id}`}>
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
