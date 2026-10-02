import { notFound, redirect } from 'next/navigation'

import { uuidFromScan } from '@/lib/scanIds'

/**
 * The permanent identifier route (spec section 7.5): `/id/{uuid}` never
 * moves. It leads to the component page, which shows the piece, its
 * tombstone, or the duplicate's canonical piece.
 */
export default async function IdPage({ params }: { params: Promise<{ uuid: string }> }) {
  const { uuid } = await params
  const id = uuidFromScan(uuid)
  if (!id) notFound()
  redirect(`/components/${id}`)
}
