import ComponentLookup from '@/components/components/ComponentLookup'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Search } from 'lucide-react'

interface FindComponentProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}

export default async function FindComponent({ searchParams }: FindComponentProps) {
  const params = await searchParams
  const referenceID =
    typeof params.reference_id === 'string' ? params.reference_id : undefined

  return (
    <div className='grid gap-[32px] m-2'>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-6 w-6" />
            Find Component
          </CardTitle>
          <CardDescription>
            Use this tool to <b>find a physical component</b> based on its <b>Component ID</b>.
          </CardDescription>
        </CardHeader>
        <CardContent className='p-1'>
          <ComponentLookup presetReferenceID={referenceID} />
        </CardContent>
      </Card>
    </div>
  )
}
