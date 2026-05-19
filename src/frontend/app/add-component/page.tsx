import ComponentAddWizard from '@/components/components/add/ComponentAddWizard'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { PackagePlus } from 'lucide-react'

export default function AddComponentPage() {
  return (
    <div className="container mx-auto max-w-3xl space-y-6 p-6">
      <div className="space-y-3">
        <div className="flex items-center gap-2 sm:gap-3">
          <PackagePlus className="h-6 w-6 text-primary" />
          <h1 className="text-xl font-bold sm:text-2xl">Add Component</h1>
        </div>
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 dark:border-blue-900 dark:bg-blue-950/30">
          <ul className="list-disc space-y-1 pl-5 text-sm text-blue-900 dark:text-blue-100">
            <li>
              <b>Scan</b> the physical tag QR code to read the pre-assigned identity id.
            </li>
            <li>
              <b>Enter</b> catalog metadata and bounding box dimensions (L × W × H in mm).
            </li>
            <li>
              <b>Capture</b> site photos with your camera or gallery, then create the catalog entry.
            </li>
          </ul>
        </div>
      </div>

      <Card className="bg-card/75 shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">New catalog entry</CardTitle>
          <CardDescription>Follow the steps below. You can go back to edit earlier steps.</CardDescription>
        </CardHeader>
        <CardContent>
          <ComponentAddWizard />
        </CardContent>
      </Card>
    </div>
  )
}
