'use client'

/**
 * Users and invitations (admin; decisions 8.14, 8.20, 8.21). Accounts show
 * their dataset memberships; the filters combine and live in the URL so a
 * view can be bookmarked. The second tab lists invitations.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSession } from 'next-auth/react'
import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { Pencil, RefreshCw, Users } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import InviteDialog from '@/components/admin/InviteDialog'
import InvitationsTable from '@/components/admin/InvitationsTable'
import { DATASET_ROLES } from '@/components/admin/RoleCheckboxes'
import type { AdminUserRow, DatasetView, InvitationView } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'

type UserRole = 'user' | 'admin'
const ANY = '__any__'
const FILTER_KEYS = ['q', 'dataset', 'dataset_role', 'no_dataset', 'role', 'state', 'invited'] as const

export default function AdminUsersPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const pathname = usePathname()
  const params = useSearchParams()
  const tab = params.get('tab') === 'invitations' ? 'invitations' : 'accounts'

  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [datasets, setDatasets] = useState<DatasetView[]>([])
  const [invitations, setInvitations] = useState<InvitationView[]>([])
  const [loading, setLoading] = useState(true)
  const [text, setText] = useState(params.get('q') ?? '')
  const [editUser, setEditUser] = useState<AdminUserRow | null>(null)
  const [editRole, setEditRole] = useState<UserRole>('user')
  const [editDisabled, setEditDisabled] = useState(false)
  const [editFullName, setEditFullName] = useState('')
  const [saving, setSaving] = useState(false)

  const isAdmin = session?.user?.role === 'admin' && !session.error
  const currentUserId = session?.user?.id ?? ''

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
      router.push('/')
    }
  }, [router, session, status])

  /** Change URL params (filters, tab); empty values are removed. */
  const setParams = useCallback((changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString())
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === '' || value === ANY) next.delete(key)
      else next.set(key, value)
    }
    const query = next.toString()
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false })
  }, [params, pathname, router])

  // the text filter applies after a short pause
  useEffect(() => {
    const timer = window.setTimeout(() => {
      if ((params.get('q') ?? '') !== text.trim()) setParams({ q: text.trim() })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [text, params, setParams])

  const userQuery = useMemo(() => {
    const query = new URLSearchParams()
    for (const key of FILTER_KEYS) {
      const value = params.get(key)
      if (value) query.set(key, value)
    }
    return query.toString()
  }, [params])

  const invitationQuery = useMemo(() => {
    const query = new URLSearchParams()
    const state = params.get('inv_state')
    const dataset = params.get('inv_dataset')
    if (state) query.set('state', state)
    if (dataset) query.set('dataset', dataset)
    return query.toString()
  }, [params])

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true)
      setUsers(await backendJson<AdminUserRow[]>(`/users${userQuery ? `?${userQuery}` : ''}`))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load users.')
    } finally {
      setLoading(false)
    }
  }, [userQuery])

  const fetchInvitations = useCallback(async () => {
    try {
      setInvitations(await backendJson<InvitationView[]>(
        `/invitations${invitationQuery ? `?${invitationQuery}` : ''}`))
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to load invitations.')
    }
  }, [invitationQuery])

  useEffect(() => {
    if (!isAdmin) return
    backendJson<DatasetView[]>('/datasets').then(setDatasets).catch(() => setDatasets([]))
  }, [isAdmin])

  useEffect(() => {
    if (isAdmin) void fetchUsers()
  }, [isAdmin, fetchUsers])

  useEffect(() => {
    if (isAdmin && tab === 'invitations') void fetchInvitations()
  }, [isAdmin, tab, fetchInvitations])

  const openEditDialog = (user: AdminUserRow) => {
    setEditUser(user)
    setEditRole((user.role ?? 'user') as UserRole)
    setEditDisabled(user.disabled === true)
    setEditFullName(user.full_name ?? '')
  }

  const handleSave = async () => {
    if (!editUser) return
    const payload: Record<string, unknown> = {}
    if (editRole !== editUser.role) payload.role = editRole
    if (editDisabled !== (editUser.disabled === true)) payload.disabled = editDisabled
    const trimmedName = editFullName.trim()
    if (trimmedName !== (editUser.full_name ?? '').trim()) payload.full_name = trimmedName
    if (Object.keys(payload).length === 0) {
      setEditUser(null)
      return
    }
    try {
      setSaving(true)
      await backendJson(`/users/${encodeURIComponent(editUser._id)}`, { method: 'PATCH', body: payload })
      toast.success('User updated.')
      setEditUser(null)
      void fetchUsers()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to update user.')
    } finally {
      setSaving(false)
    }
  }

  const isEditingSelf = editUser?._id === currentUserId
  const datasetName = (slug: string) => datasets.find((d) => d._id === slug)?.name ?? slug

  return (
    <div className="container mx-auto space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Users className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">Users and invitations</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Accounts with their dataset memberships, and the invitations sent.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void (tab === 'accounts' ? fetchUsers() : fetchInvitations())}
          disabled={loading}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <Tabs value={tab} onValueChange={(value) => setParams({ tab: value === 'accounts' ? null : value })}>
        <TabsList>
          <TabsTrigger value="accounts">Accounts</TabsTrigger>
          <TabsTrigger value="invitations">Invitations</TabsTrigger>
        </TabsList>

        <TabsContent value="accounts">
          <Card>
            <CardHeader>
              <CardTitle>Accounts</CardTitle>
              <CardDescription>
                {users.length} account{users.length === 1 ? '' : 's'} match the filters
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <Input
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="Username, name or email..."
                  className="w-full max-w-xs"
                  aria-label="Search accounts"
                />
                <FilterSelect label="Dataset" value={params.get('dataset')}
                  onChange={(v) => setParams({ dataset: v, no_dataset: null })}
                  options={datasets.map((d) => ({ value: d._id, label: d.name }))} />
                <FilterSelect label="Dataset role" value={params.get('dataset_role')}
                  onChange={(v) => setParams({ dataset_role: v, no_dataset: null })}
                  options={DATASET_ROLES.map((r) => ({ value: r.value, label: r.label }))} />
                <FilterSelect label="Global role" value={params.get('role')}
                  onChange={(v) => setParams({ role: v })}
                  options={[{ value: 'user', label: 'User' }, { value: 'admin', label: 'Admin' }]} />
                <FilterSelect label="State" value={params.get('state')}
                  onChange={(v) => setParams({ state: v })}
                  options={[
                    { value: 'enabled', label: 'Enabled' },
                    { value: 'disabled', label: 'Disabled' },
                    { value: 'unverified', label: 'Unverified' },
                  ]} />
                <FilterCheck id="f-no-dataset" label="No dataset" checked={params.get('no_dataset') === 'true'}
                  onChange={(c) => setParams({ no_dataset: c ? 'true' : null, dataset: null, dataset_role: null })} />
                <FilterCheck id="f-invited" label="Invited" checked={params.get('invited') === 'true'}
                  onChange={(c) => setParams({ invited: c ? 'true' : null })} />
              </div>

              {loading ? (
                <div className="flex min-h-[240px] items-center justify-center">
                  <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
                </div>
              ) : users.length === 0 ? (
                <p className="py-8 text-center text-muted-foreground">No accounts match the filters.</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Username</TableHead>
                      <TableHead>Name / email</TableHead>
                      <TableHead>Datasets</TableHead>
                      <TableHead>Role</TableHead>
                      <TableHead>State</TableHead>
                      <TableHead className="w-[60px]" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((user) => (
                      <TableRow key={user._id}>
                        <TableCell className="font-medium">
                          {user.username}
                          {user._id === currentUserId && (
                            <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                          )}
                          {user.invited && <Badge variant="outline" className="ml-2 text-[10px]">invited</Badge>}
                        </TableCell>
                        <TableCell className="text-xs">
                          <div>{user.full_name ?? '—'}</div>
                          <div className="text-muted-foreground">{user.email ?? '—'}</div>
                        </TableCell>
                        <TableCell className="text-xs">
                          {(user.memberships ?? []).length === 0 ? (
                            <span className="text-muted-foreground">—</span>
                          ) : (
                            <div className="flex flex-wrap gap-1">
                              {(user.memberships ?? []).map((m) => (
                                <Badge key={m.dataset} variant="secondary" className="text-[10px]">
                                  {datasetName(m.dataset)}: {m.roles.join(', ')}
                                </Badge>
                              ))}
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>{user.role}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge variant={user.disabled ? 'destructive' : user.email_verified ? 'outline' : 'secondary'}>
                            {user.disabled ? 'Disabled' : user.email_verified ? 'Enabled' : 'Unverified'}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          <Button variant="outline" size="sm" onClick={() => openEditDialog(user)}
                            aria-label={`Edit ${user.username}`}>
                            <Pencil className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="invitations">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Invitations</CardTitle>
                <CardDescription>
                  Registration outside the open domains works only with an invitation.
                </CardDescription>
              </div>
              <InviteDialog datasets={datasets} allowNoDataset onInvited={() => void fetchInvitations()} />
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-end gap-3">
                <FilterSelect label="State" value={params.get('inv_state')}
                  onChange={(v) => setParams({ inv_state: v })}
                  options={['open', 'used', 'expired', 'revoked'].map((s) => ({ value: s, label: s }))} />
                <FilterSelect label="Dataset" value={params.get('inv_dataset')}
                  onChange={(v) => setParams({ inv_dataset: v })}
                  options={datasets.map((d) => ({ value: d._id, label: d.name }))} />
              </div>
              <InvitationsTable invitations={invitations} onChanged={() => void fetchInvitations()} />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <Dialog open={editUser !== null} onOpenChange={(open) => { if (!open) setEditUser(null) }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit user</DialogTitle>
            <DialogDescription>
              {editUser ? `Account settings of ${editUser.username}. Dataset roles are set on the dataset's page.` : ''}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="edit-full-name">Full name</Label>
              <Input id="edit-full-name" value={editFullName}
                onChange={(event) => setEditFullName(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-role">Global role</Label>
              <Select value={editRole} onValueChange={(value) => setEditRole(value as UserRole)}
                disabled={isEditingSelf}>
                <SelectTrigger id="edit-role" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
              {isEditingSelf && <p className="text-xs text-muted-foreground">You cannot change your own role.</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-disabled">Account state</Label>
              <Select value={editDisabled ? 'disabled' : 'active'}
                onValueChange={(value) => setEditDisabled(value === 'disabled')} disabled={isEditingSelf}>
                <SelectTrigger id="edit-disabled" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Enabled</SelectItem>
                  <SelectItem value="disabled">Disabled</SelectItem>
                </SelectContent>
              </Select>
              {isEditingSelf && <p className="text-xs text-muted-foreground">You cannot disable your own account.</p>}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditUser(null)} disabled={saving}>Cancel</Button>
            <Button onClick={() => void handleSave()} disabled={saving}>Save changes</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string | null
  onChange: (value: string | null) => void
  options: { value: string; label: string }[]
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <Select value={value ?? ANY} onValueChange={(v) => onChange(v === ANY ? null : v)}>
        <SelectTrigger className="h-9 w-40"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>Any</SelectItem>
          {options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  )
}

function FilterCheck({
  id,
  label,
  checked,
  onChange,
}: {
  id: string
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <div className="flex h-9 items-center gap-2">
      <Checkbox id={id} checked={checked} onCheckedChange={(c) => onChange(c === true)} />
      <Label htmlFor={id} className="text-sm font-normal">{label}</Label>
    </div>
  )
}
