'use client'

import { Badge } from '@/components/ui/badge'
import { WriteButton } from '@/components/ui/write-button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  canRenew,
  canRevoke,
  scopeText,
  tokenPreview,
  type AccessTokenRow,
  type AdminAccessTokenRow,
} from '@/lib/accessTokens'
import { formatTimestamp } from '@/lib/utils'

/**
 * The list of access tokens, for Settings (own tokens) and the admin page
 * (every token, with the owner). A row shows the first 8 characters of the
 * token, never the token itself: the rows hold no token, and only the answer of
 * a create or a renew does (once). The buttons are write buttons, so they stop
 * while the backend is read-only. In a narrow card the table scrolls sideways
 * and the buttons stay in view at its right edge.
 */
export default function AccessTokenTable({
  rows,
  showOwner = false,
  onRevoke,
  onRenew,
  busyId,
}: {
  rows: (AccessTokenRow | AdminAccessTokenRow)[]
  showOwner?: boolean
  onRevoke: (row: AccessTokenRow) => void
  onRenew?: (row: AccessTokenRow) => void
  busyId?: string | null
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Token</TableHead>
          <TableHead>Name</TableHead>
          {showOwner && <TableHead>Owner</TableHead>}
          <TableHead>Scope</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Last used</TableHead>
          <TableHead>Expires</TableHead>
          <TableHead className="sticky right-0 w-[150px] bg-card" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.id}>
            <TableCell className="font-mono text-xs">{tokenPreview(row)}</TableCell>
            <TableCell className="font-medium">{row.name}</TableCell>
            {showOwner && (
              <TableCell className="text-xs">{(row as AdminAccessTokenRow).owner_username ?? '-'}</TableCell>
            )}
            <TableCell className="text-xs">{scopeText(row.scopes)}</TableCell>
            <TableCell className="whitespace-nowrap text-xs">{formatTimestamp(row.created)}</TableCell>
            <TableCell className="whitespace-nowrap text-xs">
              {row.last_used ? formatTimestamp(row.last_used) : <span className="text-muted-foreground">never</span>}
            </TableCell>
            <TableCell className="whitespace-nowrap text-xs">
              {formatTimestamp(row.expires)}
              {row.status === 'expired' && <Badge variant="destructive" className="ml-2 text-[10px]">expired</Badge>}
              {row.status === 'revoked' && <Badge variant="secondary" className="ml-2 text-[10px]">revoked</Badge>}
              {row.status === 'active' && row.renew_due && (
                <Badge variant="outline" className="ml-2 text-[10px]">expires soon</Badge>
              )}
            </TableCell>
            <TableCell className="sticky right-0 space-x-1 bg-card text-right">
              {onRenew && canRenew(row) && (
                <WriteButton size="sm" variant="outline" disabled={busyId === row.id} onClick={() => onRenew(row)}>
                  Renew
                </WriteButton>
              )}
              {canRevoke(row) && (
                <WriteButton size="sm" variant="outline" disabled={busyId === row.id} onClick={() => onRevoke(row)}>
                  Revoke
                </WriteButton>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
