// app/auth/signin/page.tsx
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

import SignInForm from './SignInForm'
import SessionExpiredNotice from '@/components/auth/SessionExpiredNotice'

type SearchParams = Promise<Record<string, string | string[] | undefined>>

function toSafePathServer(raw: string | string[] | undefined): string {
  const fallback = '/dashboard'
  const val = Array.isArray(raw) ? raw[0] : raw
  if (!val) return fallback
  // allow only same-origin relative paths
  if (val.startsWith('/')) return val
  return fallback
}

export default async function Page({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams
  const callbackUrl = toSafePathServer(sp?.callbackUrl)
  return (
    <div>
      <SessionExpiredNotice />
      <SignInForm callbackUrl={callbackUrl} />
    </div>
  )
}
