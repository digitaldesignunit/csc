'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import React from 'react'

function ComponentOverviewDataTableFilterCell({ param, value, titletext }: { param: string, value: string , titletext: string}) {
  // Now we can safely use React hooks
  const router = useRouter()
  const searchParams = useSearchParams()

  function handleClick() {
    const params = new URLSearchParams(searchParams.toString())
    params.set(`${param}`, value)
    router.replace(`?${params.toString()}`)
  }

  return (
    <div
      className="inline-flex max-w-full items-center gap-1 rounded px-1.5 py-0.5 text-xs
                 bg-muted text-foreground hover:bg-accent hover:text-accent-foreground
                 truncate cursor-pointer"
      onClick={handleClick}
      title={titletext}
    >
      {value}
    </div>
  )
}

export default ComponentOverviewDataTableFilterCell