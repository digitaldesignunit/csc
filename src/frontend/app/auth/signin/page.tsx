// app/auth/signin/page.tsx
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

import BackgroundMesh from '@/components/components/BackgroundMesh'
import SignInForm from './SignInForm'
import SessionExpiredNotice from '@/components/auth/SessionExpiredNotice'
import { safeCallbackPath } from '@/lib/safeCallback'

type SearchParams = Promise<Record<string, string | string[] | undefined>>

export default async function Page({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams
  const callbackUrl = safeCallbackPath(sp?.callbackUrl, '/my-work')
  return (
    <div className="relative min-h-[80vh] md:min-h-[90vh]">
      {/* Background Mesh */}
      <BackgroundMesh
        className="absolute inset-0 -z-10"
        opacity={0.08}
        rotationSpeed={0.15}
        intensity={0.2}
        scale={1.1}
      />
      <SessionExpiredNotice />
      <SignInForm callbackUrl={callbackUrl} />
    </div>
  )
}
