import ComponentIdentifier from '@/components/components/ComponentIdentifier'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { QrCode } from 'lucide-react'

export default function IdentifyComponent() {
  return (
    <div className='grid gap-[32px] m-2'>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <QrCode className="h-6 w-6" />
            Identify Component
          </CardTitle>
          <CardDescription>
            Scan the QR code of a <b>physical component</b> to access its <b>digital representation</b>, details and information.
          </CardDescription>
        </CardHeader>
        <CardContent className='p-1'>
          <ComponentIdentifier />
        </CardContent>
      </Card>
    </div>
  )
}
