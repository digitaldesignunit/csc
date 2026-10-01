import { Card, CardContent } from '@/components/ui/card'
import { PackagePlus } from 'lucide-react'

/**
 * Adding components is paused while the catalog moves to the 0.6 data
 * model: the 0.5 wizard wrote through a retired route. It returns as the
 * 0.6 snapshot form (new component / cut from / record new state /
 * correct, plan P7); `ComponentAddWizard` is its starting point.
 */
export default function AddComponentPage() {
  return (
    <div className="container mx-auto max-w-3xl space-y-4 p-4 sm:space-y-6 sm:p-6">
      <div className="flex items-center gap-2 sm:gap-3">
        <PackagePlus className="h-6 w-6 text-primary" />
        <h1 className="text-xl font-bold sm:text-2xl">Add Component</h1>
      </div>
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          Adding components is paused while the catalog moves to its new data model.
          It returns with the new snapshot form.
        </CardContent>
      </Card>
    </div>
  )
}
