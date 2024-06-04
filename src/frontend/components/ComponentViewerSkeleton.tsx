'use client'

import { Skeleton } from '@/components/ui/skeleton'
import { Card } from './ui/card'

export default function ComponentViewerSkeleton() {
  return (
    <Card className='flex h-[40dvh] m-2'>
      <div className='flex flex-col space-y-3 grow'>
        <Skeleton className='h-full rounded-xl m-2 flex items-center justify-center'>
          <strong>Loading Geometry...</strong>
        </Skeleton>
      </div>
    </Card>
  )
}
