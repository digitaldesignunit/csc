'use client'

/**
 * The materials list for admin (spec section 2.10, section 7.7, I25;
 * decision 8.35): add, edit, retire, delete while unused, merge into
 * another one. A new default class re-derives every derived waste class;
 * a merge moves every component and leaves the old id as an alias.
 */
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Combine, Layers, Pencil, Plus, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
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
import { Field, VocabSelect } from '@/components/lineage/fields'
import type { Material } from '@/generated/LineageModels'
import { MATERIAL_GROUP_LABELS, type MaterialGroup } from '@/generated/Vocab'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'

type Editing = { mode: 'create' } | { mode: 'edit'; material: Material }

function MaterialDialog({ editing, onClose, onSaved }: {
  editing: Editing
  onClose: () => void
  onSaved: () => void
}) {
  const initial = editing.mode === 'edit' ? editing.material : null
  const [id, setId] = useState(initial?._id ?? '')
  const [label, setLabel] = useState(initial?.label ?? '')
  const [group, setGroup] = useState<MaterialGroup>((initial?.group ?? 'mineral') as MaterialGroup)
  const [defaultClass, setDefaultClass] = useState(initial?.default_class ?? '17 ')
  const [uniclass, setUniclass] = useState(initial?.uniclass ?? '')
  const [notes, setNotes] = useState(initial?.notes ?? '')
  const [retired, setRetired] = useState(initial?.retired ?? false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    setBusy(true)
    setError(null)
    const fields = {
      label: label.trim(),
      group,
      default_class: defaultClass.trim(),
      uniclass: uniclass.trim() || null,
      notes: notes.trim() || null,
    }
    try {
      if (editing.mode === 'create') {
        await backendJson('/materials', { method: 'POST', body: { _id: id.trim(), ...fields } })
        toast.success(`Added ${fields.label}`)
      } else {
        const result = await backendJson<{ identities_rederived?: number }>(
          `/materials/${encodeURIComponent(editing.material._id)}`,
          { method: 'PATCH', body: { ...fields, retired } })
        const n = result.identities_rederived ?? 0
        toast.success(n ? `Saved; ${n} component(s) took the new waste class` : 'Saved')
      }
      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Saving failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose() }}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing.mode === 'create' ? 'Add a material' : `Edit ${initial?.label}`}</DialogTitle>
          <DialogDescription>
            Generic materials only; products go into a component&apos;s trade name.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {editing.mode === 'create' && (
            <Field label="Id" htmlFor="material-id" hint="Lower case with underscores; it never changes.">
              <Input id="material-id" value={id} onChange={(event) => setId(event.target.value)}
                placeholder="e.g. glass_fibre_concrete" />
            </Field>
          )}
          <Field label="Label" htmlFor="material-label">
            <Input id="material-label" value={label} onChange={(event) => setLabel(event.target.value)} />
          </Field>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Field label="Group" htmlFor="material-group">
              <VocabSelect id="material-group" labels={MATERIAL_GROUP_LABELS} value={group}
                onChange={(value) => value && setGroup(value)} />
            </Field>
            <Field label="Default waste class" htmlFor="material-class"
              hint="EU List of Waste, never a hazardous (*) entry.">
              <Input id="material-class" value={defaultClass}
                onChange={(event) => setDefaultClass(event.target.value)} />
            </Field>
          </div>
          <Field label="Uniclass" htmlFor="material-uniclass">
            <Input id="material-uniclass" value={uniclass} onChange={(event) => setUniclass(event.target.value)}
              placeholder="e.g. Ma_40_19" />
          </Field>
          <Field label="Notes" htmlFor="material-notes">
            <Textarea id="material-notes" rows={2} value={notes} onChange={(event) => setNotes(event.target.value)} />
          </Field>
          {editing.mode === 'edit' && (
            <label className="flex items-center gap-2 text-sm">
              <Checkbox checked={retired} onCheckedChange={(checked) => setRetired(checked === true)} />
              Retired: hidden from forms; components using it keep it
            </label>
          )}
          {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={() => void save()} disabled={busy}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MergeDialog({ source, materials, onClose, onSaved }: {
  source: Material
  materials: Material[]
  onClose: () => void
  onSaved: () => void
}) {
  const targets = materials.filter((m) => m._id !== source._id && !m.merged_into)
  const [into, setInto] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const merge = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await backendJson<{ identities_moved: number }>(
        `/materials/${encodeURIComponent(source._id)}/merge`, { method: 'POST', body: { into } })
      toast.success(`Merged; ${result.identities_moved} component(s) moved`)
      onSaved()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Merge failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !busy) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Merge {source.label}</DialogTitle>
          <DialogDescription>
            Every component using it moves to the target. Derived waste classes follow the
            target&apos;s default; classes set by hand stay. The old id remains as an alias.
            This cannot be undone here.
          </DialogDescription>
        </DialogHeader>
        <Field label="Into" htmlFor="merge-into">
          <Select value={into} onValueChange={setInto}>
            <SelectTrigger id="merge-into" className="w-full">
              <SelectValue placeholder="Pick the material to keep" />
            </SelectTrigger>
            <SelectContent>
              {targets.map((m) => (
                <SelectItem key={m._id} value={m._id}>{m.label} ({m.default_class})</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button variant="destructive" onClick={() => void merge()} disabled={busy || !into}>Merge</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function MaterialsPage() {
  const router = useRouter()
  const { me, loading: meLoading, isAdmin } = useMe()
  const [materials, setMaterials] = useState<Material[]>([])
  const [loading, setLoading] = useState(true)
  const [showAll, setShowAll] = useState(false)
  const [editing, setEditing] = useState<Editing | null>(null)
  const [merging, setMerging] = useState<Material | null>(null)

  useEffect(() => {
    if (!meLoading && me && !isAdmin) router.push('/')
  }, [me, meLoading, isAdmin, router])

  const load = useCallback(async () => {
    try {
      setMaterials(await backendJson<Material[]>('/materials?include_retired=true&include_merged=true'))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not load materials')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isAdmin) void load()
  }, [isAdmin, load])

  const remove = async (material: Material) => {
    if (!window.confirm(`Delete ${material.label}? Only possible while no component uses it.`)) return
    try {
      await backendJson(`/materials/${encodeURIComponent(material._id)}`, { method: 'DELETE' })
      toast.success(`Deleted ${material.label}`)
      void load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Delete failed')
    }
  }

  const shown = materials.filter((m) => showAll || (!m.retired && !m.merged_into))
  const hidden = materials.length - materials.filter((m) => !m.retired && !m.merged_into).length

  return (
    <div className="container mx-auto max-w-4xl space-y-4 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold sm:text-2xl">Materials</h1>
        </div>
        <Button size="sm" onClick={() => setEditing({ mode: 'create' })}>
          <Plus className="mr-1 h-4 w-4" />Add material
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        The controlled materials list. Each material gives components its default waste class.
      </p>
      {hidden > 0 && (
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={showAll} onCheckedChange={(checked) => setShowAll(checked === true)} />
          Show {hidden} retired or merged
        </label>
      )}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <ul className="space-y-2">
          {shown.map((material) => (
            <li key={material._id}>
              <Card className="py-0">
                <CardContent className="flex flex-wrap items-center justify-between gap-3 p-3">
                  <div className="min-w-0 space-y-0.5">
                    <p className="flex flex-wrap items-center gap-2 font-medium">
                      {material.label}
                      <Badge variant="secondary">{material.group}</Badge>
                      {material.retired && !material.merged_into && <Badge variant="outline">retired</Badge>}
                      {material.merged_into && <Badge variant="outline">merged into {material.merged_into}</Badge>}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-mono">{material._id}</span>
                      {' --- '}{material.default_class}
                      {material.uniclass ? ` --- ${material.uniclass}` : ''}
                    </p>
                    {material.notes && <p className="text-xs text-muted-foreground">{material.notes}</p>}
                  </div>
                  {!material.merged_into && (
                    <div className="flex gap-1">
                      <Button size="sm" variant="ghost" title="Edit"
                        onClick={() => setEditing({ mode: 'edit', material })}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="ghost" title="Merge into another material"
                        onClick={() => setMerging(material)}>
                        <Combine className="h-4 w-4" />
                      </Button>
                      <Button size="sm" variant="ghost" title="Delete (only while unused)"
                        onClick={() => void remove(material)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
      {editing && (
        <MaterialDialog editing={editing} onClose={() => setEditing(null)} onSaved={() => void load()} />
      )}
      {merging && (
        <MergeDialog source={merging} materials={materials} onClose={() => setMerging(null)}
          onSaved={() => void load()} />
      )}
    </div>
  )
}
