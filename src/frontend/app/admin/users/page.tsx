'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import { Pencil, RefreshCw, Users } from 'lucide-react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
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

type UserRole = 'user' | 'admin'

type AdminUserRow = {
  id: string
  username: string
  email?: string | null
  full_name?: string | null
  disabled?: boolean | null
  role: UserRole
  email_verified: boolean
}

function userId(row: AdminUserRow): string {
  return row.id
}

function parseUsersPayload(data: unknown): AdminUserRow[] {
  if (!Array.isArray(data)) return []
  return data.flatMap((item) => {
    if (!item || typeof item !== 'object') return []
    const row = item as Record<string, unknown>
    const id = typeof row.id === 'string'
      ? row.id
      : typeof row._id === 'string'
        ? row._id
        : ''
    const username = typeof row.username === 'string' ? row.username : ''
    if (!id || !username) return []
    const role: UserRole = row.role === 'admin' ? 'admin' : 'user'
    return [{
      id,
      username,
      email: typeof row.email === 'string' ? row.email : null,
      full_name: typeof row.full_name === 'string' ? row.full_name : null,
      disabled: typeof row.disabled === 'boolean' ? row.disabled : null,
      role,
      email_verified: row.email_verified === true,
    }]
  })
}

export default function AdminUsersPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [users, setUsers] = useState<AdminUserRow[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [editUser, setEditUser] = useState<AdminUserRow | null>(null)
  const [editRole, setEditRole] = useState<UserRole>('user')
  const [editDisabled, setEditDisabled] = useState(false)
  const [editFullName, setEditFullName] = useState('')
  const [saving, setSaving] = useState(false)

  const currentUserId = session?.user?.id ?? ''

  useEffect(() => {
    if (status === 'loading') return
    if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
      router.push('/')
    }
  }, [router, session, status])

  const fetchUsers = useCallback(async () => {
    try {
      setLoading(true)
      const response = await fetch('/api/backend/users', { credentials: 'include' })
      if (!response.ok) {
        throw new Error(`Failed to load users (${response.status})`)
      }
      const data = await response.json()
      setUsers(parseUsersPayload(data))
    } catch (error) {
      console.error('Failed to fetch users:', error)
      toast.error('Failed to load users.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (session?.user?.role === 'admin' && !session.error) {
      void fetchUsers()
    }
  }, [fetchUsers, session])

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return users
    return users.filter((user) => (
      user.username.toLowerCase().includes(query)
      || (user.email ?? '').toLowerCase().includes(query)
      || (user.full_name ?? '').toLowerCase().includes(query)
      || user.id.toLowerCase().includes(query)
    ))
  }, [search, users])

  const openEditDialog = (user: AdminUserRow) => {
    setEditUser(user)
    setEditRole(user.role)
    setEditDisabled(user.disabled === true)
    setEditFullName(user.full_name ?? '')
  }

  const closeEditDialog = () => {
    setEditUser(null)
    setSaving(false)
  }

  const handleSave = async () => {
    if (!editUser) return

    const payload: Record<string, unknown> = {}
    if (editRole !== editUser.role) payload.role = editRole
    if (editDisabled !== (editUser.disabled === true)) payload.disabled = editDisabled
    const trimmedName = editFullName.trim()
    if (trimmedName !== (editUser.full_name ?? '').trim()) {
      payload.full_name = trimmedName
    }

    if (Object.keys(payload).length === 0) {
      toast.message('No changes to save.')
      closeEditDialog()
      return
    }

    try {
      setSaving(true)
      const response = await fetch(
        `/api/backend/users/${encodeURIComponent(userId(editUser))}`,
        {
          method: 'PATCH',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )

      if (!response.ok) {
        const error = (await response.json().catch(() => null)) as { detail?: string } | null
        toast.error(error?.detail || 'Failed to update user.')
        return
      }

      const updated = parseUsersPayload([await response.json()])[0]
      if (updated) {
        setUsers((prev) => prev.map((row) => (
          userId(row) === updated.id ? updated : row
        )))
      }
      toast.success('User updated.')
      closeEditDialog()
    } catch (error) {
      console.error('Failed to update user:', error)
      toast.error('Failed to update user.')
    } finally {
      setSaving(false)
    }
  }

  const isEditingSelf = editUser?.id === currentUserId

  return (
    <div className="container mx-auto space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <Users className="h-6 w-6 text-primary" />
            <h1 className="text-2xl font-bold">User Management</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            View accounts, assign roles, and enable or disable access.
          </p>
        </div>
        <Button variant="outline" onClick={() => void fetchUsers()} disabled={loading}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
          <CardDescription>
            {users.length} registered user{users.length === 1 ? '' : 's'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by username, email, name, or ID…"
            className="max-w-md"
          />

          {loading ? (
            <div className="flex min-h-[240px] items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
            </div>
          ) : filteredUsers.length === 0 ? (
            <p className="py-8 text-center text-muted-foreground">No users match your search.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Username</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Full name</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Verified</TableHead>
                  <TableHead className="w-[100px]">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredUsers.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium">
                      {user.username}
                      {user.id === currentUserId && (
                        <span className="ml-2 text-xs text-muted-foreground">(you)</span>
                      )}
                    </TableCell>
                    <TableCell>{user.email ?? '—'}</TableCell>
                    <TableCell>{user.full_name ?? '—'}</TableCell>
                    <TableCell>
                      <Badge variant={user.role === 'admin' ? 'default' : 'secondary'}>
                        {user.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={user.disabled ? 'destructive' : 'outline'}>
                        {user.disabled ? 'Disabled' : 'Active'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={user.email_verified ? 'outline' : 'secondary'}>
                        {user.email_verified ? 'Verified' : 'Pending'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => openEditDialog(user)}
                      >
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

      <Dialog open={editUser !== null} onOpenChange={(open) => !open && closeEditDialog()}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit user</DialogTitle>
            <DialogDescription>
              {editUser ? `Update account settings for ${editUser.username}.` : ''}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="edit-full-name">Full name</Label>
              <Input
                id="edit-full-name"
                value={editFullName}
                onChange={(event) => setEditFullName(event.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-role">Role</Label>
              <Select
                value={editRole}
                onValueChange={(value) => setEditRole(value as UserRole)}
                disabled={isEditingSelf}
              >
                <SelectTrigger id="edit-role" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="user">User</SelectItem>
                  <SelectItem value="admin">Admin</SelectItem>
                </SelectContent>
              </Select>
              {isEditingSelf && (
                <p className="text-xs text-muted-foreground">
                  You cannot change your own role.
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-disabled">Account status</Label>
              <Select
                value={editDisabled ? 'disabled' : 'active'}
                onValueChange={(value) => setEditDisabled(value === 'disabled')}
                disabled={isEditingSelf}
              >
                <SelectTrigger id="edit-disabled" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="disabled">Disabled</SelectItem>
                </SelectContent>
              </Select>
              {isEditingSelf && (
                <p className="text-xs text-muted-foreground">
                  You cannot disable your own account.
                </p>
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={closeEditDialog} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={() => void handleSave()} disabled={saving}>
              Save changes
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
