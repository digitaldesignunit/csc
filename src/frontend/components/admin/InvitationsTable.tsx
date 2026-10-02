'use client'

/** Invitations with their state; open ones can be revoked (8.14, 8.21). */
import { toast } from 'sonner'
import { Ban } from 'lucide-react'

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
import type { InvitationView } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { formatTimestamp } from '@/lib/utils'

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
          <TableHead className="w-[60px]" />
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
            </TableCell>
            <TableCell className="text-xs">{formatTimestamp(invitation.created)}</TableCell>
            <TableCell className="text-xs">{formatTimestamp(invitation.expires_at)}</TableCell>
            <TableCell>
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
