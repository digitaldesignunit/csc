'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import React from 'react'

function ComponentOverviewDataTableCell({ param, value, titletext }: { param: string, value: string , titletext: string}) {
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
      className="text-left align-text-top underline cursor-pointer"
      onClick={handleClick}
      title={titletext}
    >
      {value}
    </div>
  )
}

export default ComponentOverviewDataTableCell