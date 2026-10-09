import Link from 'next/link'
import { Archive, EyeOff, Lock, PackageX, TimerOff } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { formatDay } from '@/lib/utils'

/**
 * What the component page shows instead of the passport (decisions 8.11,
 * 8.17, spec section 7.5): whoever scans a tag holds the piece, so a piece
 * the viewer cannot see is explained, not hidden behind a 404.
 */
export type ComponentAccessNoticeProps =
  | { kind: 'not-public'; callbackUrl: string }
  | { kind: 'no-access' }
  | { kind: 'purged' }
  | { kind: 'withdrawn'; withdrawnAt?: string | null; catalogNumber?: number | null }
  | { kind: 'no-current-state'; catalogNumber?: number | null }

export default function ComponentAccessNotice(props: ComponentAccessNoticeProps) {
  const { icon: Icon, title, text } = describe(props)
  return (
    <div className="container mx-auto max-w-xl p-6">
      <Card>
        <CardContent className="space-y-4 p-6">
          <div className="flex items-center gap-2">
            <Icon className="h-6 w-6 text-muted-foreground" />
            <h1 className="text-lg font-semibold">{title}</h1>
          </div>
          <p className="text-sm text-muted-foreground">{text}</p>
          <div className="flex flex-wrap gap-2">
            {props.kind === 'not-public' && (
              <Button asChild size="sm">
                <Link href={`/auth/signin?callbackUrl=${encodeURIComponent(props.callbackUrl)}`}>
                  Sign in
                </Link>
              </Button>
            )}
            <Button asChild size="sm" variant="outline">
              <Link href="/">About the catalog</Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function describe(props: ComponentAccessNoticeProps) {
  switch (props.kind) {
    case 'not-public':
      return {
        icon: Lock,
        title: 'This component is not public',
        text: 'It belongs to a project of the Catalog of Second Chances. Sign in to see it if you are a member or the project shares it with registered users.',
      }
    case 'no-access':
      return {
        icon: EyeOff,
        title: 'You have no access to this component',
        text: 'It belongs to a project you are not a member of. Ask the project\'s moderator if you need access.',
      }
    case 'purged':
      return {
        icon: PackageX,
        title: 'This component was removed',
        text: 'Its record was deleted from the catalog for good. The link stays known so it does not lead anywhere else.',
      }
    case 'withdrawn':
      return {
        icon: Archive,
        title: `Component${props.catalogNumber != null ? ` #${props.catalogNumber}` : ''} was withdrawn`,
        text: `It was withdrawn from the catalog${props.withdrawnAt ? ` on ${formatDay(props.withdrawnAt)}` : ''}. Its record is kept; members of its project can still see it.`,
      }
    case 'no-current-state':
      return {
        icon: TimerOff,
        title: `Component${props.catalogNumber != null ? ` #${props.catalogNumber}` : ''} has no current state`,
        text: 'None of its recorded states is published at the moment.',
      }
  }
}
