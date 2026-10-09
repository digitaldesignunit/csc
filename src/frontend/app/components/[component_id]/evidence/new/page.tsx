import EvidenceForm from '@/components/evidence/form/EvidenceForm'
import { uuidFromScan } from '@/lib/scanIds'
import { notFound } from 'next/navigation'

/**
 * The evidence form (spec 7.6): reached from the component page, on a phone
 * right after a tag scan. `?correct=<evidence id>` opens it as a correction
 * of a published record; `?edit=<evidence id>` opens a draft (or, for a
 * moderator, a pending record) to change it (8.127); `?method=` opens it
 * with a method picked.
 */
export default async function NewEvidencePage({
  params,
  searchParams,
}: {
  params: Promise<{ component_id: string }>
  searchParams: Promise<{ correct?: string; edit?: string; method?: string }>
}) {
  const { component_id } = await params
  const { correct, edit, method } = await searchParams
  const id = uuidFromScan(component_id)
  if (!id) notFound()
  const correctId = typeof correct === 'string' ? uuidFromScan(correct) ?? undefined : undefined
  const editId = typeof edit === 'string' ? uuidFromScan(edit) ?? undefined : undefined
  const initialMethod = typeof method === 'string' && /^[a-z_]{1,64}$/.test(method) ? method : undefined
  return (
    <EvidenceForm
      identityId={id}
      correctId={editId ? undefined : correctId}
      editId={editId}
      initialMethod={initialMethod}
    />
  )
}
