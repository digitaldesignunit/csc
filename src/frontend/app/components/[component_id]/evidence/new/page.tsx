import EvidenceForm from '@/components/evidence/form/EvidenceForm'
import { uuidFromScan } from '@/lib/scanIds'
import { notFound } from 'next/navigation'

/**
 * The evidence form (spec 7.6): reached from the component page, on a phone
 * right after a tag scan. `?correct=<evidence id>` opens it as a correction
 * of a published record.
 */
export default async function NewEvidencePage({
  params,
  searchParams,
}: {
  params: Promise<{ component_id: string }>
  searchParams: Promise<{ correct?: string }>
}) {
  const { component_id } = await params
  const { correct } = await searchParams
  const id = uuidFromScan(component_id)
  if (!id) notFound()
  const correctId = typeof correct === 'string' ? uuidFromScan(correct) ?? undefined : undefined
  return <EvidenceForm identityId={id} correctId={correctId} />
}
