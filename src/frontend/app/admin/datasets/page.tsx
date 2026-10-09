'use client'

/**
 * Datasets (spec section 3.6, section 7.7): admin sees and creates all;
 * a moderator sees the datasets they moderate and manages them.
 */
import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Database, Plus } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import type { DatasetView } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { browseUrl } from '@/lib/browse'
import { datasetCounts } from '@/lib/datasets'
import { useMe } from '@/lib/me'

export default function DatasetsPage() {
  const router = useRouter()
  const { me, loading: meLoading, isAdmin, moderates, moderatesAny } = useMe()
  const [datasets, setDatasets] = useState<DatasetView[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!meLoading && me && !moderatesAny) router.push('/')
  }, [me, meLoading, moderatesAny, router])

  const load = useCallback(async () => {
    try {
      const all = await backendJson<DatasetView[]>('/datasets')
      setDatasets(all.filter((d) => moderates(d._id)))
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not load datasets')
    } finally {
      setLoading(false)
    }
  }, [moderates])

  useEffect(() => {
    if (moderatesAny) void load()
  }, [moderatesAny, load])

  return (
    <div className="container mx-auto max-w-4xl space-y-4 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Database className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold sm:text-2xl">Datasets</h1>
        </div>
        {isAdmin && <CreateDatasetDialog onCreated={(slug) => router.push(`/admin/datasets/${slug}`)} />}
      </div>
      <p className="text-sm text-muted-foreground">
        A dataset is a project: its members, their roles and who sees its components.
        {isAdmin ? ' You see all datasets as admin.' : ' You see the datasets you moderate.'}
      </p>
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <ul className="space-y-2">
          {datasets.map((dataset) => (
            <li key={dataset._id}>
              <Card>
                <CardContent className="space-y-3 p-3 text-sm">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium">{dataset.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {dataset._id}
                        {datasetCounts(dataset) && <>, {datasetCounts(dataset)}</>}
                      </div>
                    </div>
                    <Badge variant={dataset.visibility === 'catalog' ? 'secondary' : 'outline'}>
                      {dataset.visibility === 'catalog' ? 'Visible to signed-in users' : 'Members only'}
                    </Badge>
                  </div>
                  <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
                    {(isAdmin || moderates(dataset._id)) && (
                      <Button asChild variant="outline" size="sm">
                        <Link href={`/admin/datasets/${encodeURIComponent(dataset._id)}`}>Edit</Link>
                      </Button>
                    )}
                    <Button asChild variant="outline" size="sm">
                      <Link href={browseUrl('dataset', dataset._id)}>Browse components</Link>
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function CreateDatasetDialog({ onCreated }: { onCreated: (slug: string) => void }) {
  const [open, setOpen] = useState(false)
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [visibility, setVisibility] = useState<'members' | 'catalog'>('members')
  const [busy, setBusy] = useState(false)

  const create = async () => {
    setBusy(true)
    try {
      await backendJson('/datasets', {
        method: 'POST',
        body: { _id: slug.trim(), name: name.trim(), description: description.trim() || null, visibility },
      })
      toast.success(`Dataset ${name} created`)
      setOpen(false)
      onCreated(slug.trim())
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not create the dataset')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}><Plus className="mr-2 h-4 w-4" />New dataset</Button>
      <Dialog open={open} onOpenChange={(next) => { if (!busy) setOpen(next) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New dataset</DialogTitle>
            <DialogDescription>The short id cannot be changed later; the name can.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="ds-slug">Id</Label>
              <Input id="ds-slug" value={slug} placeholder="e.g. lichtwiese_survey"
                onChange={(event) => setSlug(event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ds-name">Name</Label>
              <Input id="ds-name" value={name} onChange={(event) => setName(event.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ds-description">Description</Label>
              <Textarea id="ds-description" rows={2} value={description}
                onChange={(event) => setDescription(event.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Who sees its components</Label>
              <Select value={visibility} onValueChange={(v) => setVisibility(v as 'members' | 'catalog')}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="members">Members only</SelectItem>
                  <SelectItem value="catalog">All signed-in users</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button>
            <Button onClick={() => void create()} disabled={busy || !slug.trim() || !name.trim()}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
