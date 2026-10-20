'use client'

import { useCallback, useEffect, useState } from 'react'
import { KeyRound, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import AccessTokenTable from '@/components/settings/AccessTokenTable'
import NewTokenNotice from '@/components/settings/NewTokenNotice'
import { useConfirm } from '@/components/common/ConfirmDialog'
import { Field, NativeSelect } from '@/components/evidence/controls'
import { WriteButton } from '@/components/ui/write-button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { backendJson } from '@/lib/backend'
import {
  createFailure,
  lifetimeLabel,
  type AccessTokenCreated,
  type AccessTokenOptions,
  type AccessTokenRow,
} from '@/lib/accessTokens'

/**
 * Settings, "Access tokens" (decision 8.167): the tokens of the signed-in
 * account. Whoever may hold a personal access token (the backend decides:
 * `CSC_PAT_ROLES`, administrators at first) gets the create form; everyone
 * sees and revokes the tokens they have. A new token is shown once, with a
 * copy button; the list only ever shows its first 8 characters.
 */
export default function AccessTokensSection() {
  const [options, setOptions] = useState<AccessTokenOptions | null>(null)
  const [rows, setRows] = useState<AccessTokenRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [days, setDays] = useState<string>('')
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [fresh, setFresh] = useState<AccessTokenCreated | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const { confirm, dialog } = useConfirm()

  const load = useCallback(async () => {
    try {
      const [opts, list] = await Promise.all([
        backendJson<AccessTokenOptions>('/auth/access-tokens/options'),
        backendJson<AccessTokenRow[]>('/auth/access-tokens'),
      ])
      setOptions(opts)
      setDays((current) => current || String(opts.default_days))
      setRows(list)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The tokens could not be loaded.')
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const create = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim()) return
    setCreating(true)
    setCreateError(null)
    try {
      const made = await backendJson<AccessTokenCreated>('/auth/access-tokens', {
        method: 'POST',
        body: { name: name.trim(), days: Number(days) },
      })
      setFresh(made)
      setName('')
      await load()
    } catch (err) {
      setCreateError(createFailure(err))
    } finally {
      setCreating(false)
    }
  }

  const revoke = async (row: AccessTokenRow) => {
    const yes = await confirm({
      title: `Revoke "${row.name}"?`,
      description: 'Anything that uses this token stops working at once. This cannot be undone.',
      confirmLabel: 'Revoke',
      destructive: true,
    })
    if (!yes) return
    setBusyId(row.id)
    try {
      await backendJson(`/auth/access-tokens/${encodeURIComponent(row.id)}`, { method: 'DELETE' })
      if (fresh?.id === row.id) setFresh(null)
      toast.success('Token revoked')
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'The token was not revoked')
    } finally {
      setBusyId(null)
    }
  }

  const renew = async (row: AccessTokenRow) => {
    const yes = await confirm({
      title: `Renew "${row.name}"?`,
      description: 'A new token with the same name is made and shown once. The old token stops working at once.',
      confirmLabel: 'Renew',
    })
    if (!yes) return
    setBusyId(row.id)
    try {
      const made = await backendJson<AccessTokenCreated>(
        `/auth/access-tokens/${encodeURIComponent(row.id)}/renew`, { method: 'POST' })
      setFresh(made)
      await load()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'The token was not renewed')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <KeyRound className="h-4 w-4 text-primary" aria-hidden />
          Access tokens
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="text-muted-foreground">
          A personal access token lets a tool such as an AI assistant read the catalog as you,
          and nothing more. It expires, and you can revoke it here at any time.
        </p>

        {error && <p className="text-destructive" role="alert">{error}</p>}
        {!options && !error && (
          <p className="inline-flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden />Loading...
          </p>
        )}

        {fresh && <NewTokenNotice name={fresh.name} token={fresh.token} onDone={() => setFresh(null)} />}

        {options?.can_create && (
          <form onSubmit={create} className="flex flex-wrap items-end gap-3">
            <Field id="token-name" label="Name" className="min-w-[12rem] flex-1">
              <Input
                id="token-name"
                value={name}
                maxLength={80}
                placeholder="e.g. my assistant"
                onChange={(event) => setName(event.target.value)}
                disabled={creating}
              />
            </Field>
            <Field id="token-days" label="Valid for" className="w-40">
              <NativeSelect
                id="token-days"
                value={days}
                onChange={setDays}
                placeholder={null}
                disabled={creating}
                options={options.lifetimes.map((d) => ({
                  value: String(d),
                  label: lifetimeLabel(d) + (d === options.default_days ? ' (default)' : ''),
                }))}
              />
            </Field>
            <WriteButton type="submit" disabled={creating || !name.trim()}>
              {creating ? 'Creating...' : 'Create token'}
            </WriteButton>
          </form>
        )}
        {createError && <p className="text-destructive" role="alert">{createError}</p>}
        {options && !options.can_create && (
          <p className="text-muted-foreground">
            Personal access tokens are available to administrators for now.
            {rows && rows.length > 0 ? ' The tokens you hold are listed below.' : ''}
          </p>
        )}

        {rows && rows.length > 0 && (
          <AccessTokenTable rows={rows} onRevoke={revoke} onRenew={renew} busyId={busyId} />
        )}
        {rows && rows.length === 0 && options?.can_create && (
          <p className="text-muted-foreground">You have no access tokens.</p>
        )}
        {options && (
          <p className="text-xs text-muted-foreground">At most {options.max_active} active tokens per account.</p>
        )}
      </CardContent>
      {dialog}
    </Card>
  )
}
