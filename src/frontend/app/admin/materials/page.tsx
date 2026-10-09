'use client'

/**
 * The materials list for admin (spec section 2.10, section 7.7, I25;
 * decision 8.35): add, edit, retire, delete while unused, merge into
 * another one. A new default class re-derives every derived waste class;
 * a merge moves every component and leaves the old id as an alias.
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Combine, Layers, MoreHorizontal, Pencil, Plus, Search, Trash2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Field, VocabSelect } from '@/components/lineage/fields'
import type { Material } from '@/generated/LineageModels'
import { MATERIAL_GROUP_LABELS, type MaterialGroup } from '@/generated/Vocab'
import { backendJson } from '@/lib/backend'
import { browseUrl } from '@/lib/browse'
import { useMe } from '@/lib/me'
import { filterMaterials, groupLabel, hiddenCount, stateNote } from '@/lib/materials'
import { useMediaQuery } from '@/hooks/useMediaQuery'

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

  const [query, setQuery] = useState('')
  const wide = useMediaQuery('(min-width: 768px)')
  const shown = filterMaterials(materials, query, showAll)
  const hidden = hiddenCount(materials)

  const browseButton = (material: Material, full = false, compact = false) => (
    <Button asChild variant="outline" size="sm" className={full ? 'w-full' : undefined}>
      <Link
        href={browseUrl('material', material._id)}
        aria-label={`Browse components of ${material.label}`}
        title={`Browse the components made of ${material.label}`}
      >
        {compact ? <><Search className="h-3.5 w-3.5" aria-hidden />Browse</> : 'Browse components'}
      </Link>
    </Button>
  )

  const rowMenu = (material: Material) => (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="ghost" aria-label={`Actions for ${material.label}`}>
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => setEditing({ mode: 'edit', material })}>
          <Pencil className="mr-2 h-4 w-4" />Edit
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setMerging(material)}>
          <Combine className="mr-2 h-4 w-4" />Merge into another material
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onSelect={() => void remove(material)}>
          <Trash2 className="mr-2 h-4 w-4" />Delete (only while unused)
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )

  return (
    <div className="mx-auto w-full max-w-5xl space-y-3 p-3 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Layers className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold sm:text-2xl">Materials</h1>
        </div>
        <Button size="sm" onClick={() => setEditing({ mode: 'create' })}>
          <Plus className="mr-1 h-4 w-4" />Add material
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-0 flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            aria-label="Search the materials"
            placeholder="Search label, id, waste class"
            className="h-9 pl-8"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        {hidden > 0 && (
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={showAll} onCheckedChange={(checked) => setShowAll(checked === true)} />
            Show {hidden} retired or merged
          </label>
        )}
      </div>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : shown.length === 0 ? (
        <Card className="p-4 text-sm text-muted-foreground">No material matches.</Card>
      ) : wide ? (
        <Card className="overflow-hidden py-0">
          {/* fixed layout: long cells truncate (the full text is the tooltip), the table never scrolls */}
          <table className="w-full table-fixed caption-bottom text-sm">
            <TableHeader>
              <TableRow>
                <TableHead>Material</TableHead>
                <TableHead className="w-28">Group</TableHead>
                <TableHead className="w-28">Waste class</TableHead>
                <TableHead className="hidden w-28 xl:table-cell">Uniclass</TableHead>
                <TableHead className="hidden w-48 xl:table-cell">Id</TableHead>
                <TableHead className="w-24"><span className="sr-only">Components</span></TableHead>
                <TableHead className="w-12"><span className="sr-only">Actions</span></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((material) => (
                <TableRow key={material._id}>
                  <TableCell className="truncate font-medium" title={material.label}>
                    {material.label}
                    {stateNote(material) && <Badge variant="outline" className="ml-2">{stateNote(material)}</Badge>}
                  </TableCell>
                  <TableCell><Badge variant="secondary" className="max-w-full truncate">{groupLabel(material.group)}</Badge></TableCell>
                  <TableCell className="truncate" title={material.default_class}>{material.default_class}</TableCell>
                  <TableCell className="hidden truncate xl:table-cell" title={material.uniclass ?? ''}>{material.uniclass ?? ''}</TableCell>
                  <TableCell className="hidden truncate font-mono text-xs text-muted-foreground xl:table-cell" title={material._id}>{material._id}</TableCell>
                  <TableCell>{!material.merged_into && browseButton(material, false, true)}</TableCell>
                  <TableCell>{!material.merged_into && rowMenu(material)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </table>
        </Card>
      ) : (
        <ul className="divide-y rounded-lg border">
          {shown.map((material) => (
            <li key={material._id} className="space-y-2 px-3 py-2">
              <div className="flex items-center gap-2">
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium">
                    {material.label}
                    <Badge variant="secondary">{groupLabel(material.group)}</Badge>
                    {stateNote(material) && <Badge variant="outline">{stateNote(material)}</Badge>}
                  </p>
                  <p className="text-xs text-muted-foreground">Waste class {material.default_class}</p>
                </div>
                {!material.merged_into && rowMenu(material)}
              </div>
              {!material.merged_into && browseButton(material, true)}
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
