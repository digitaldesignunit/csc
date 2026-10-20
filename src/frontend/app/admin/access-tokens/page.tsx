'use client'

/**
 * Access tokens of every account (decision 8.167 f), for admins: the owner's
 * user name (no e-mail address), the first 8 characters of the token, scope,
 * created, last used, expiry. An admin revokes any token; nobody sees a token
 * itself.
 */
import { useCallback, useEffect, useState } from 'react'
import { KeyRound, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import AccessTokenTable from '@/components/settings/AccessTokenTable'
import { useConfirm } from '@/components/common/ConfirmDialog'
import { Card } from '@/components/ui/card'
import { backendJson } from '@/lib/backend'
import type { AccessTokenRow, AdminAccessTokenRow } from '@/lib/accessTokens'

export default function AdminAccessTokensPage() {
  const [rows, setRows] = useState<AdminAccessTokenRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const { confirm, dialog } = useConfirm()

  const load = useCallback(async () => {
    try {
      setRows(await backendJson<AdminAccessTokenRow[]>('/admin/access-tokens'))
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The tokens could not be loaded.')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const revoke = async (row: AccessTokenRow) => {
    const owner = (row as AdminAccessTokenRow).owner_username
    const yes = await confirm({
      title: `Revoke "${row.name}"?`,
      description: `Anything that uses this token${owner ? ` of ${owner}` : ''} stops working at once. This cannot be undone.`,
      confirmLabel: 'Revoke',
      destructive: true,
    })
    if (!yes) return
    setBusyId(row.id)
    try {
      await backendJson(`/admin/access-tokens/${encodeURIComponent(row.id)}`, { method: 'DELETE' })
      toast.success('Token revoked')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'The token was not revoked')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-4 p-3 sm:p-5">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
          <KeyRound className="h-6 w-6 text-primary" aria-hidden />Access tokens
        </h1>
        <p className="text-sm text-muted-foreground">
          Every personal access token of every account. A token itself is shown once to its owner and
          never again.
        </p>
      </div>
      <Card className="p-3">
        {error && <p className="text-sm text-destructive" role="alert">{error}</p>}
        {!rows && !error && (
          <p className="inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />Loading...
          </p>
        )}
        {rows && rows.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">No access tokens yet.</p>}
        {rows && rows.length > 0 && (
          <AccessTokenTable rows={rows} showOwner onRevoke={revoke} busyId={busyId} />
        )}
      </Card>
      {dialog}
    </div>
  )
}
