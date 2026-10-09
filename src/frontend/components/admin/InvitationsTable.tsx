'use client'

/**
 * Invitations with their state; open ones can be revoked (8.14, 8.21), an
 * open or expired one can be resent with a new code, and one whose mail did
 * not go out says so (8.124 b). The link itself is never shown.
 */
import { toast } from 'sonner'
import { Ban, MailWarning, RefreshCw } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import type { InvitationView, InviteResult } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { resendNotice } from '@/lib/mailResult'
import { formatDay } from '@/lib/utils'

const STATE_VARIANT: Record<InvitationView['state'], 'default' | 'secondary' | 'outline' | 'destructive'> = {
  open: 'default',
  used: 'secondary',
  expired: 'outline',
  revoked: 'destructive',
}

export default function InvitationsTable({
  invitations,
  onChanged,
  showDataset = true,
}: {
  invitations: InvitationView[]
  onChanged: () => void
  showDataset?: boolean
}) {
  const revoke = async (invitation: InvitationView) => {
    try {
      await backendJson(`/invitations/${invitation._id}`, { method: 'DELETE' })
      toast.success(`Invitation for ${invitation.email} revoked`)
      onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Revoke failed')
    }
  }

  const resend = async (invitation: InvitationView) => {
    try {
      const result = await backendJson<InviteResult>(`/invitations/${invitation._id}/resend`, { method: 'POST' })
      const notice = resendNotice({ email: invitation.email, result: result.result })
      if (notice.warning) toast.warning(notice.text)
      else toast.success(notice.text)
      onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Resend failed')
    }
  }

  if (invitations.length === 0) {
    return <p className="py-6 text-center text-sm text-muted-foreground">No invitations.</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Email</TableHead>
          {showDataset && <TableHead>Dataset</TableHead>}
          <TableHead>Roles</TableHead>
          <TableHead>State</TableHead>
          <TableHead>Sent</TableHead>
          <TableHead>Expires</TableHead>
          <TableHead className="w-[96px]" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {invitations.map((invitation) => (
          <TableRow key={invitation._id}>
            <TableCell className="font-medium">{invitation.email}</TableCell>
            {showDataset && <TableCell>{invitation.dataset ?? '—'}</TableCell>}
            <TableCell className="text-xs">{invitation.roles.join(', ') || '—'}</TableCell>
            <TableCell>
              <Badge variant={STATE_VARIANT[invitation.state]}>{invitation.state}</Badge>
              {invitation.mail_failed && invitation.state !== 'used' && invitation.state !== 'revoked' && (
                <Badge variant="outline" className="ml-1.5 border-destructive/50 text-destructive">
                  <MailWarning className="mr-1 h-3 w-3" aria-hidden />mail failed
                </Badge>
              )}
            </TableCell>
            <TableCell className="text-xs">{formatDay(invitation.created)}</TableCell>
            <TableCell className="text-xs">{formatDay(invitation.expires_at)}</TableCell>
            <TableCell className="whitespace-nowrap">
              {(invitation.state === 'open' || invitation.state === 'expired') && (
                <Button
                  size="sm"
                  variant={invitation.mail_failed ? 'outline' : 'ghost'}
                  aria-label={`Resend the invitation to ${invitation.email}`}
                  title="Resend: a new code, the old link stops working"
                  onClick={() => void resend(invitation)}
                >
                  <RefreshCw className="h-4 w-4" />
                </Button>
              )}
              {invitation.state === 'open' && (
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={`Revoke invitation for ${invitation.email}`}
                  title="Revoke"
                  onClick={() => void revoke(invitation)}
                >
                  <Ban className="h-4 w-4" />
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
