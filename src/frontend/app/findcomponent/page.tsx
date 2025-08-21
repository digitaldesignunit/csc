import ComponentLookup from '@/components/components/ComponentLookup'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface FindComponentProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}

export default async function FindComponent({ searchParams }: FindComponentProps) {
  const params = await searchParams
  const referenceID =
    typeof params.reference_id === 'string' ? params.reference_id : undefined

  return (
    <div className='grid gap-[32px] m-4'>
      <Card>
        <CardHeader>
          <CardTitle>Find Component</CardTitle>
          <CardDescription>
            Use this tool to compare QR codes and find components within the physical repository.
          </CardDescription>
        </CardHeader>
        <CardContent className='p-1'>
          <ComponentLookup presetReferenceID={referenceID} />
        </CardContent>
      </Card>
    </div>
  )
}
