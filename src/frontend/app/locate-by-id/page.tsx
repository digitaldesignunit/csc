import ComponentLocateById from '@/components/components/ComponentLocateById'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { QrCode, Search } from 'lucide-react'

interface LocateByIdProps {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}

export default async function LocateByIdPage({ searchParams }: LocateByIdProps) {
  const params = await searchParams
  const referenceID =
    typeof params.reference_id === 'string' ? params.reference_id : undefined

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-6xl">
      {/* Header */}
      <div className="mb-3 sm:mb-4">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Search className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Locate by ID</h1>
        </div>
        <div className="mt-3 rounded-lg border bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800 p-3">
          <ul className="list-disc space-y-1 pl-5 text-sm sm:text-base text-blue-800 dark:text-blue-200">
            <li>
              <b>Purpose:</b>{' '}Find the <b>physical</b> part of a selected <b>digital
              component</b>.
            </li>
            <li>
              <b>Input:</b>{' '}First set the <b>reference ID</b> (scan or manual
              input), then scan <b>physical QR codes</b> for comparison.
            </li>
            <li>
              <b>Result:</b>{' '}The scanner confirms when a scanned physical part
              ID matches the reference ID.
            </li>
          </ul>
        </div>
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
              Use your device&apos;s camera to scan component QR codes
            </CardDescription>
          </CardHeader>
          <CardContent className='p-1'>
            <ComponentLocateById presetReferenceID={referenceID} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
