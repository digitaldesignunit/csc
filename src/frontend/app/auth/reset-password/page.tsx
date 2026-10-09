// app/auth/reset-password/page.tsx
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

import BackgroundMesh from '@/components/components/BackgroundMesh'
import ResetPasswordForm from './ResetPasswordForm'

type SearchParams = Promise<Record<string, string | string[] | undefined>>

/** The link of the reset mail: `?token=...` (decision 8.124 a). */
export default async function Page({ searchParams }: { searchParams: SearchParams }) {
  const sp = await searchParams
  const raw = sp?.token
  const token = (Array.isArray(raw) ? raw[0] : raw) ?? ''
  return (
    <div className="relative min-h-[80vh] md:min-h-[90vh]">
      <BackgroundMesh className="absolute inset-0 -z-10" opacity={0.08} rotationSpeed={0.15} intensity={0.2} />
      <ResetPasswordForm token={token} />
    </div>
  )
}
