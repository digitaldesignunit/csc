'use client'

import { KeyRound, UserRound } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { Membership } from '@/generated/AccessModels'
import { accountRows, membershipLine } from '@/lib/account'
import { useMe } from '@/lib/me'

/** Settings, "Account" (plan P11 stage 3, decision 8.118 S6): who I am and what I may do, from my own data. */
export default function AccountSection() {
  const { me, loading, isAdmin } = useMe()
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <UserRound className="h-4 w-4 text-primary" aria-hidden />
          Account
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!me ? (
          <p className="text-muted-foreground">{loading ? 'Loading...' : 'Sign in to see your account.'}</p>
        ) : (
          <>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
              {accountRows(me).map((row) => (
                <div key={row.label} className="contents">
                  <dt className="text-muted-foreground">{row.label}</dt>
                  <dd className="min-w-0 break-words">{row.value}</dd>
                </div>
              ))}
            </dl>
            <div className="space-y-1.5">
              <p className="flex items-center gap-1.5 font-medium">
                <KeyRound className="h-3.5 w-3.5" aria-hidden />
                Datasets and roles
              </p>
              {isAdmin ? (
                <p className="text-muted-foreground">Administrator: all datasets, all roles.</p>
              ) : me.memberships.length === 0 ? (
                <p className="text-muted-foreground">You are not a member of a dataset yet. Ask a moderator to add you.</p>
              ) : (
                <ul className="space-y-1">
                  {me.memberships.map((m: Membership) => (
                    <li key={m.dataset} className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium">{m.name || m.dataset}</span>
                      {m.roles.map((role) => (
                        <Badge key={role} variant="secondary" className="capitalize">{role}</Badge>
                      ))}
                      <span className="sr-only">{membershipLine(m)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
