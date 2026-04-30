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
    <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-2">
      <div className="flex items-center gap-2">
        <div className="shrink-0 text-xs font-medium text-foreground">Open by ID</div>
        <div className="flex-1">
          <Input
            id="component-uuid"
            type="text"
            placeholder="Paste component UUID..."
            className="h-9 bg-background placeholder:text-xs border-primary/40 focus-visible:ring-primary/40"
            value={uuid}
            onChange={(e) => setUuid(e.target.value)}
            onKeyDown={handleKeyDown}
          />
        </div>
        <Button onClick={handleNavigate} disabled={!uuid.trim()} className="h-9 min-w-[80px] px-3">
          <Search className="h-4 w-4" />
          <span className="ml-1">Open</span>
        </Button>
      </div>
    </div>
  )
}
