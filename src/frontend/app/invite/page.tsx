'use client'

/**
 * The link of an invitation mail (decision 8.144 b). One page for every
 * recipient: signed in with the address the invitation names, the account
 * sees what it offers and accepts (the consent); signed out, the visitor signs
 * in and comes back here, or creates an account with the code. The page says
 * nothing about a code to anyone it is not addressed to.
 */
import { Suspense, useEffect, useState } from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { signOut, useSession } from 'next-auth/react'
import { CheckCircle, Loader2, MailOpen, XCircle } from 'lucide-react'

import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Button } from '@/components/ui/button'
import { WriteButton } from '@/components/ui/write-button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { InvitationAccepted, InvitationPreview } from '@/generated/AccessModels'
import { backendJson } from '@/lib/backend'
import { inviteCode, offerText, registerHref, rolesText, signInHref } from '@/lib/invite'

type Offer = InvitationPreview
type Accepted = InvitationAccepted

function Frame({ icon, title, description, children }: {
  icon: React.ReactNode
  title: string
  description?: string
  children: React.ReactNode
}) {
  return (
    <div className="relative flex min-h-[70vh] items-start justify-center p-4 pt-8 sm:items-center sm:pt-4 md:min-h-[88vh]">
      <BackgroundMesh className="absolute inset-0 -z-10" opacity={0.08} rotationSpeed={0.15} intensity={0.2} />
      <Card className="w-full max-w-md bg-card/75">
        <CardHeader className="text-center">
          <div className="mb-3 flex justify-center">{icon}</div>
          <CardTitle className="text-2xl">{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent className="space-y-4">{children}</CardContent>
      </Card>
    </div>
  )
}

function InviteContent() {
  const params = useSearchParams()
  const code = inviteCode(params.get('code'))
  const { data: session, status } = useSession()
  const [offer, setOffer] = useState<Offer | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [accepted, setAccepted] = useState<Accepted | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!code || status !== 'authenticated') return
    let cancelled = false
    backendJson<Offer>('/invitations/preview', { method: 'POST', body: { code } })
      .then((body) => { if (!cancelled) setOffer(body) })
      .catch((err) => { if (!cancelled) setRefusal(err instanceof Error ? err.message : 'The invitation could not be read.') })
    return () => { cancelled = true }
  }, [code, status])

  const accept = async () => {
    if (!code) return
    setBusy(true)
    setError(null)
    try {
      setAccepted(await backendJson<Accepted>('/invitations/accept', { method: 'POST', body: { code } }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The invitation could not be accepted.')
    } finally {
      setBusy(false)
    }
  }

  if (!code) {
    return (
      <Frame icon={<XCircle className="h-14 w-14 text-red-600 dark:text-red-400" aria-hidden />} title="This link is incomplete">
        <p className="text-center text-sm text-muted-foreground">
          Open the link in the invitation mail as it is, or ask the person who invited you to send it again.
        </p>
      </Frame>
    )
  }

  if (status === 'loading') {
    return (
      <Frame icon={<Loader2 className="h-14 w-14 animate-spin text-primary" aria-hidden />} title="One moment">
        <p className="text-center text-sm text-muted-foreground">Checking your sign-in.</p>
      </Frame>
    )
  }

  if (status === 'unauthenticated') {
    return (
      <Frame
        icon={<MailOpen className="h-14 w-14 text-primary" aria-hidden />}
        title="You are invited"
        description="to the Catalog of Second Chances"
      >
        <p className="text-center text-sm text-muted-foreground">
          If you already have an account, sign in with the address this invitation was sent to and accept it.
          If you do not have one, create it here: the invitation then comes with it.
        </p>
        <div className="flex flex-col gap-2">
          <Link href={signInHref(code)}><Button className="w-full">Sign in to accept</Button></Link>
          <Link href={registerHref(code)}><Button variant="outline" className="w-full">Create an account</Button></Link>
        </div>
      </Frame>
    )
  }

  if (accepted) {
    return (
      <Frame icon={<CheckCircle className="h-14 w-14 text-green-600 dark:text-green-400" aria-hidden />} title="Invitation accepted">
        <p className="text-center text-sm">
          {accepted.dataset_name
            ? <>You are now {rolesText(accepted.roles)} in the dataset &quot;{accepted.dataset_name}&quot;.</>
            : <>Your account is ready.</>}
        </p>
        <div className="flex flex-col gap-2">
          <Link href="/components"><Button className="w-full">Open the catalogue</Button></Link>
          <Link href="/my-work"><Button variant="outline" className="w-full">My work</Button></Link>
        </div>
      </Frame>
    )
  }

  if (refusal) {
    const name = session?.user?.username ?? 'your account'
    return (
      <Frame icon={<XCircle className="h-14 w-14 text-red-600 dark:text-red-400" aria-hidden />} title="This invitation does not fit">
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/20 dark:text-red-200">
          {refusal}
        </div>
        <p className="text-center text-sm text-muted-foreground">
          You are signed in as {name}. An invitation works for the address it was sent to only: sign in with that
          account, or create one with it.
        </p>
        <div className="flex flex-col gap-2">
          <Button variant="outline" onClick={() => void signOut({ callbackUrl: signInHref(code) })}>
            Sign out and use another account
          </Button>
          <Link href="/components"><Button variant="ghost" className="w-full">Back to the catalogue</Button></Link>
        </div>
      </Frame>
    )
  }

  if (!offer) {
    return (
      <Frame icon={<Loader2 className="h-14 w-14 animate-spin text-primary" aria-hidden />} title="Reading the invitation">
        <p className="text-center text-sm text-muted-foreground">One moment.</p>
      </Frame>
    )
  }

  return (
    <Frame
      icon={<MailOpen className="h-14 w-14 text-primary" aria-hidden />}
      title="You are invited"
      description={offer.inviter_name ? `by ${offer.inviter_name}` : undefined}
    >
      <p className="text-center text-sm">{offerText(offer)}</p>
      <p className="text-center text-xs text-muted-foreground">
        Accepting gives your account these roles. The invitation works once and expires on {offer.expires_at.slice(0, 10)}.
      </p>
      {error && <p role="alert" className="text-center text-sm text-destructive">{error}</p>}
      <div className="flex flex-col gap-2">
        <WriteButton onClick={() => void accept()} disabled={busy}>
          {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />}Accept the invitation
        </WriteButton>
        <Link href="/components"><Button variant="ghost" className="w-full">Not now</Button></Link>
      </div>
    </Frame>
  )
}

export default function InvitePage() {
  return (
    <Suspense fallback={null}>
      <InviteContent />
    </Suspense>
  )
}
