import ComponentLookup from '@/components/ComponentLookup'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

interface FindComponentProps {
  searchParams: { [key: string]: string | string[] | undefined }
}

export default function FindComponent({ searchParams }: FindComponentProps) {
  const referenceID =
    typeof searchParams.reference_id === 'string' ? searchParams.reference_id : undefined

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
