import { redirect } from 'next/navigation'

type PageParams = { component_id: string }

/**
 * The 0.5 metadata editor wrote through a retired route. Editing returns in
 * plan P7 as the 0.6 edit form (mutable metadata: name, notes, location,
 * colour); until then this path leads back to the component page.
 */
export default async function ComponentEditPage({
  params,
}: {
  params: Promise<PageParams>
}) {
  const { component_id } = await params
  redirect(`/components/${encodeURIComponent(component_id)}`)
}
