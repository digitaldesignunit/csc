import { redirect } from 'next/navigation'

/** Locate by ID moved into the Scan page (decision 8.118 Q7); a reference id in the link stays. */
export default async function LocateRedirect({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
  const params = await searchParams
  const reference = typeof params.reference_id === 'string' ? params.reference_id : ''
  redirect(`/scan?mode=locate${reference ? `&reference_id=${encodeURIComponent(reference)}` : ''}`)
}
