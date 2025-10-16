import ComponentLookup from '@/components/components/ComponentLookup'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { QrCode, Search } from 'lucide-react'

interface FindComponentProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}

export default async function FindComponent({ searchParams }: FindComponentProps) {
  const params = await searchParams
  const referenceID =
    typeof params.reference_id === 'string' ? params.reference_id : undefined

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-6xl">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Search className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Find Component</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          Use this tool to <b>find a physical component</b> based on its <b>Component ID</b>.
        </p>
      </div>

      {/* Main Content */}
      <div className="space-y-6">
        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <QrCode className="h-5 w-5" />
              QR Code Scanner
            </CardTitle>
            <CardDescription>
              Use your device's camera to scan component QR codes
            </CardDescription>
          </CardHeader>
          <CardContent className='p-1'>
            <ComponentLookup presetReferenceID={referenceID} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
