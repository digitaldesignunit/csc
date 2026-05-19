import ComponentIdTransmitter from '@/components/idtransmission/ComponentIdTransmitter'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Send, QrCode } from 'lucide-react'

export default function TransmitIdPage() {
  return (
    <div className="container mx-auto p-6 space-y-6 max-w-6xl">
      {/* Header */}
      <div className="mb-3 sm:mb-4">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Send className="h-6 w-6 text-primary" />
          <h1 className="text-xl sm:text-2xl font-bold">
            Transmit ID to Grasshopper
          </h1>
        </div>
        <div className="mt-3 rounded-lg border bg-purple-50 dark:bg-purple-950/20 border-purple-200 dark:border-purple-800 p-3">
          <ul className="list-disc space-y-1 pl-5 text-sm sm:text-base text-purple-800 dark:text-purple-200">
            <li>
              <b>Purpose:</b>{' '}Transmit a <b>scanned ID</b> into your active <b>CAD workflow</b>.
            </li>
            <li>
              <b>Input:</b>{' '}Scan QR code or paste an identity id (physical tag UUID).
            </li>
            <li>
              <b>Result:</b>{' '}The id is queued and can be consumed in
              CAD (i.e. Grasshopper) when creating a new catalog entry.
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
              Use your device&apos;s camera to scan a QR code, then
              transmit the identity id to CAD.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-1">
            <ComponentIdTransmitter />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
