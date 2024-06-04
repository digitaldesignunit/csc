import ComponentLookup from '@/components/ComponentLookup'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function FindComponent() {
  return (
    <div className='grid gap-[32px] m-4'>
      <Card>
        <CardHeader>
          <CardTitle>Find Component</CardTitle>
          <CardDescription>Use this tool to compare QR codes and find components withing the physical repository.</CardDescription>
        </CardHeader>
          <CardContent className='p-1'>
            <ComponentLookup />
          </CardContent>
      </Card>
    </div>
  )
}