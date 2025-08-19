// app/auth/signin/page.tsx
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

import SignInForm from './SignInForm'

type SearchParams = Promise<Record<string, string | string[] | undefined>>

export default async function Page({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams
  const raw = sp?.callbackUrl
  const callbackUrl =
    typeof raw === 'string' ? raw : Array.isArray(raw) ? raw[0] : '/'

  return <SignInForm callbackUrl={callbackUrl} />
}
