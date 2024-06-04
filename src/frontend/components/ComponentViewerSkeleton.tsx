import { Skeleton } from "@/components/ui/skeleton"
import { Card } from "./ui/card"

export default function ComponentViewerSkeleton() {
  return (
    <Card className='flex h-[40dvh] m-2'>
      <div className="flex flex-col space-y-3">
        <Skeleton className="h-full w-full rounded-xl" />
        <div className="space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </div>
      </div>
    </Card>
  )
}
