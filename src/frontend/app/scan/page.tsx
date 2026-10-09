import ScanPageClient from '@/components/scan/ScanPageClient'

export const dynamic = 'force-dynamic'

/** One Scan page with the modes Identify / Locate / Transmit (decision 8.118 Q7). */
export default async function ScanPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const params = await searchParams
  const mode = typeof params.mode === 'string' ? params.mode : ''
  const reference = typeof params.reference_id === 'string' ? params.reference_id : undefined
  return <ScanPageClient initialMode={mode} referenceId={reference} />
}
