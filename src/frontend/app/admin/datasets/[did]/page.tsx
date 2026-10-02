'use client'

/**
 * One dataset (moderator(D) and admin; spec section 7.7, decisions 8.14,
 * 8.20): its name, description and visibility, the member list with roles,
 * adding people by email (admin may search accounts), and its invitations.
 */
import { use, useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { ArrowLeft, Database, Search, Trash2, UserPlus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import InviteDialog from '@/components/admin/InviteDialog'
import InvitationsTable from '@/components/admin/InvitationsTable'
import RoleCheckboxes, { type DatasetRole } from '@/components/admin/RoleCheckboxes'
import type {
  DatasetMemberView,
  DatasetView,
  InvitationView,
  MemberByEmailResult,
  UserHit,
} from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { useMe } from '@/lib/me'

export default function DatasetPage({ params }: { params: Promise<{ did: string }> }) {
  const { did } = use(params)
  const { me, isAdmin, moderates, refresh: refreshMe } = useMe()
  const [dataset, setDataset] = useState<DatasetView | null>(null)
  const [invitations, setInvitations] = useState<InvitationView[]>([])
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setDataset(await backendJson<DatasetView>(`/datasets/${encodeURIComponent(did)}`))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load the dataset')
    }
  }, [did])

  const loadInvitations = useCallback(async () => {
    try {
      setInvitations(await backendJson<InvitationView[]>(`/invitations?dataset=${encodeURIComponent(did)}`))
    } catch {
      setInvitations([])
    }
  }, [did])

  useEffect(() => {
    void load()
  }, [load])

  const canManage = moderates(did)
  useEffect(() => {
    if (canManage) void loadInvitations()
  }, [canManage, loadInvitations])

  if (error) {
    return <div className="container mx-auto max-w-4xl p-6 text-sm text-destructive">{error}</div>
  }
  if (!dataset || !me) {
    return <div className="container mx-auto max-w-4xl p-6 text-sm text-muted-foreground">Loading...</div>
  }

  const afterMembers = async () => {
    await load()
    await loadInvitations()
    await refreshMe()
  }

  return (
    <div className="container mx-auto max-w-4xl space-y-6 p-6">
      <div className="space-y-1">
        <Link href="/admin/datasets" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:underline">
          <ArrowLeft className="h-3 w-3" />Datasets
        </Link>
        <div className="flex items-center gap-2">
          <Database className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold sm:text-2xl">{dataset.name}</h1>
        </div>
        <p className="text-xs text-muted-foreground">{dataset._id}</p>
      </div>

      {canManage ? (
        <>
          <DatasetSettings dataset={dataset} onSaved={(next) => setDataset(next)} />
          <MembersCard dataset={dataset} isAdmin={isAdmin} onChanged={() => void afterMembers()} />
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Invitations</CardTitle>
                <CardDescription>Sent into this dataset; open ones can be revoked.</CardDescription>
              </div>
              <InviteDialog datasets={[dataset]} fixedDataset={dataset._id} onInvited={() => void loadInvitations()} />
            </CardHeader>
            <CardContent>
              <InvitationsTable invitations={invitations} showDataset={false} onChanged={() => void loadInvitations()} />
            </CardContent>
          </Card>
        </>
      ) : (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            {dataset.description || 'No description.'} Only its moderators manage it.
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function DatasetSettings({ dataset, onSaved }: { dataset: DatasetView; onSaved: (d: DatasetView) => void }) {
  const [name, setName] = useState(dataset.name)
  const [description, setDescription] = useState(dataset.description ?? '')
  const [visibility, setVisibility] = useState(dataset.visibility)
  const [busy, setBusy] = useState(false)
  const dirty = name !== dataset.name || description !== (dataset.description ?? '') || visibility !== dataset.visibility

  const save = async () => {
    setBusy(true)
    try {
      onSaved(await backendJson<DatasetView>(`/datasets/${encodeURIComponent(dataset._id)}`, {
        method: 'PATCH',
        body: { name: name.trim(), description: description.trim() || null, visibility },
      }))
      toast.success('Dataset saved')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
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
          <Label>Who sees its published components</Label>
          <Select value={visibility} onValueChange={(v) => setVisibility(v as DatasetView['visibility'])}>
            <SelectTrigger className="w-full sm:w-80"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="members">Members only (and pieces marked public)</SelectItem>
              <SelectItem value="catalog">All signed-in users</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Button size="sm" onClick={() => void save()} disabled={busy || !dirty || !name.trim()}>Save</Button>
      </CardContent>
    </Card>
  )
}

function MembersCard({
  dataset,
  isAdmin,
  onChanged,
}: {
  dataset: DatasetView
  isAdmin: boolean
  onChanged: () => void
}) {
  const members = dataset.members ?? []
  const setRoles = async (member: DatasetMemberView, roles: DatasetRole[]) => {
    if (roles.length === 0 && !window.confirm(`Remove ${member.username ?? member.email} from ${dataset.name}?`)) return
    try {
      await backendJson(`/datasets/${encodeURIComponent(dataset._id)}/members/${member.user_id}`, {
        method: 'PUT',
        body: { roles },
      })
      toast.success(roles.length ? 'Roles saved' : 'Member removed')
      onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not change the roles')
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Members</CardTitle>
        <CardDescription>
          Roles are a set: contributors add records, reviewers check evidence, moderators publish and manage members.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AddMember dataset={dataset} isAdmin={isAdmin} onAdded={onChanged} />
        {members.length === 0 ? (
          <p className="text-sm text-muted-foreground">No members yet.</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Person</TableHead>
                <TableHead>Roles</TableHead>
                <TableHead className="w-[60px]" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {members.map((member) => (
                <TableRow key={member.user_id}>
                  <TableCell className="text-sm">
                    <div className="font-medium">
                      {member.full_name || member.username || 'Unknown account'}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {member.username ? `${member.username} · ${member.email ?? ''}` : member.user_id}
                    </div>
                  </TableCell>
                  <TableCell>
                    <RoleCheckboxes
                      idPrefix={`m-${member.user_id}`}
                      compact
                      value={member.roles as DatasetRole[]}
                      onChange={(roles) => void setRoles(member, roles)}
                    />
                  </TableCell>
                  <TableCell>
                    <Button size="sm" variant="ghost" aria-label={`Remove ${member.username}`}
                      onClick={() => void setRoles(member, [])}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * Add by exact email (8.20): an existing account joins at once and is
 * notified; any other address is invited. Admins may search accounts.
 */
function AddMember({
  dataset,
  isAdmin,
  onAdded,
}: {
  dataset: DatasetView
  isAdmin: boolean
  onAdded: () => void
}) {
  const [email, setEmail] = useState('')
  const [roles, setRoles] = useState<DatasetRole[]>(['contributor'])
  const [busy, setBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<UserHit[]>([])

  useEffect(() => {
    if (!isAdmin || query.trim().length < 2) {
      setHits([])
      return
    }
    const timer = window.setTimeout(() => {
      backendJson<UserHit[]>(`/users/search?q=${encodeURIComponent(query.trim())}`)
        .then(setHits)
        .catch(() => setHits([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [isAdmin, query])

  const add = async () => {
    setBusy(true)
    try {
      const result = await backendJson<MemberByEmailResult>(
        `/datasets/${encodeURIComponent(dataset._id)}/members`,
        { method: 'POST', body: { email: email.trim(), roles } },
      )
      toast.success(result.result === 'added'
        ? `${result.email} added and notified`
        : `No account for ${result.email}: invitation sent`)
      setEmail('')
      onAdded()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not add the person')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <UserPlus className="h-4 w-4" />Add a person
      </div>
      {isAdmin && (
        <div className="space-y-1">
          <Label htmlFor="member-search" className="text-xs text-muted-foreground">Search accounts (admin)</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input id="member-search" className="pl-8" value={query} placeholder="username, name or email"
              onChange={(event) => setQuery(event.target.value)} />
          </div>
          {hits.length > 0 && (
            <ul className="max-h-40 overflow-y-auto rounded-md border text-sm">
              {hits.map((hit) => (
                <li key={hit._id}>
                  <button type="button" className="w-full px-2 py-1 text-left hover:bg-muted"
                    onClick={() => { setEmail(hit.email ?? ''); setQuery(''); setHits([]) }}>
                    {hit.full_name || hit.username}
                    <span className="ml-2 text-xs text-muted-foreground">{hit.email}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="member-email">Email address</Label>
        <Input id="member-email" type="email" value={email} placeholder="the exact address"
          onChange={(event) => setEmail(event.target.value)} />
        <p className="text-xs text-muted-foreground">
          An existing account is added right away; any other address gets an invitation.
        </p>
      </div>
      <RoleCheckboxes idPrefix="add-member" compact value={roles} onChange={setRoles} />
      <Button size="sm" onClick={() => void add()} disabled={busy || !email.trim() || roles.length === 0}>
        Add
      </Button>
    </div>
  )
}
