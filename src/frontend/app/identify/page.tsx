import ComponentIdentifier from '@/components/components/ComponentIdentifier'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { QrCode } from 'lucide-react'

export default function IdentifyComponent() {
  return (
    <div className="container mx-auto p-6 space-y-6 max-w-6xl">
      {/* Header */}
      <div className="mb-3 sm:mb-4">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <QrCode className="h-6 w-6 text-primary" />
          <h1 className="text-xl sm:text-2xl font-bold">Scan & Identify</h1>
        </div>
        <div className="mt-3 rounded-lg border bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800 p-3">
          <ul className="list-disc space-y-1 pl-5 text-sm sm:text-base text-green-800 dark:text-green-200">
            <li>
              <b>Purpose:</b>{' '}Identify the <b>digital representation</b> of a <b>physical</b> component.
            </li>
            <li>
              <b>Input:</b>{' '}Scan the physical component&apos;s QR code.
            </li>
            <li>
              <b>Result:</b>{' '}Open the matching digital component entry with its
              catalog data, geometry, and metadata.
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
            <ComponentIdentifier />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
