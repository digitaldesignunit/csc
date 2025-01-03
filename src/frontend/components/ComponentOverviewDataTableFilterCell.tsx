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
      className="text-left align-text-top cursor-pointer text-xs hover:text-gray-500"
      onClick={handleClick}
      title={titletext}
    >
      {value}
    </div>
  )
}

export default ComponentOverviewDataTableFilterCell