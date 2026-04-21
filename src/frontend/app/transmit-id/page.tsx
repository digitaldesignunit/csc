import ComponentIdTransmitter from '@/components/ghtransmit/ComponentIdTransmitter'
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
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Send className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">
            Transmit ID to Grasshopper
          </h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          Scan the QR code of a <b>physical part</b> and transmit its
          component ID to Grasshopper. Grasshopper can then read the pending
          ID while you add the component to the catalog. The ID stays pending
          until the component is successfully added.
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
              Use your device&apos;s camera to scan a component QR code, then
              transmit the ID to Grasshopper.
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
