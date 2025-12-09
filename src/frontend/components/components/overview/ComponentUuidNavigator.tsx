'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Search } from 'lucide-react'

export default function ComponentUuidNavigator() {
  const router = useRouter()
  const [uuid, setUuid] = useState('')

  const handleNavigate = () => {
    const trimmedUuid = uuid.trim()
    if (trimmedUuid) {
      router.push(`/components/${trimmedUuid}`)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleNavigate()
    }
  }

  return (
    <div className="flex items-end gap-2">
      <div className="flex-1 space-y-2">
        <Input
          id="component-uuid"
          type="text"
          placeholder="Enter a component UUID to directly open its detail page..."
          className="placeholder:text-xs sm:placeholder:text-sm"
          value={uuid}
          onChange={(e) => setUuid(e.target.value)}
          onKeyDown={handleKeyDown}
        />
      </div>
      <Button onClick={handleNavigate} disabled={!uuid.trim()}>
        <Search className="h-4 w-4" />
        Open
      </Button>
    </div>
  )
}
