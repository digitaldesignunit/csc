'use client'

import React, { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface ComponentOverviewFilterMenuProps {
  defaultMaterial: string
  defaultCompType: string
}

/**
 * A client component that displays a small filter form
 * for "material" and "comptype". When the user clicks "Apply",
 * it updates the search params in the URL, causing the server component
 * (page.tsx) to re-fetch with new filters.
 */
export default function ComponentOverviewFilterMenu({
  defaultMaterial,
  defaultCompType,
}: ComponentOverviewFilterMenuProps) {
  const [material, setMaterial] = useState(defaultMaterial)
  const [compType, setCompType] = useState(defaultCompType)

  const router = useRouter()
  const searchParams = useSearchParams()

  function handleApplyFilters() {
    const params = new URLSearchParams(searchParams.toString())
    // Update the search params
    params.set('material', material)
    params.set('comptype', compType)
    // Optionally reset the page to 1
    params.set('page', '1')

    // Replace the URL so we don't keep adding history entries
    router.replace(`?${params.toString()}`)
  }

  return (
    <Card className="p-4 flex flex-col gap-2 max-w-[600px]">
      <div className="grid grid-cols-2 gap-2">
        {/* Material Filter */}
        <div className="flex flex-col gap-2">
          <Label htmlFor="materialInput">Material</Label>
          <Input
            id="materialInput"
            placeholder="Filter by Material..."
            value={material}
            onChange={(e) => setMaterial(e.target.value)}
          />
        </div>

        {/* Component Type Filter */}
        <div className="flex flex-col gap-2">
          <Label htmlFor="comptypeInput">Component Type</Label>
          <Input
            id="comptypeInput"
            placeholder="Filter by Component Type..."
            value={compType}
            onChange={(e) => setCompType(e.target.value)}
          />
        </div>
      </div>

      <Button onClick={handleApplyFilters}>
        Apply Filters
      </Button>
    </Card>
  )
}
