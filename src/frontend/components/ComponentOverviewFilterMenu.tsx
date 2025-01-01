'use client'

import React, { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'

interface ComponentOverviewFilterMenuProps {
  defaultMaterial: string
  defaultCompType: string
}

/**
 * A client component that displays a small filter form
 * for "material" and "comptype". When the user clicks "Apply",
 * it updates the search params in the URL, causing the server component
 * (page.tsx) to re-fetch with new filters.
 *
 * - Has a "Reset" button to clear filters.
 * - Automatically updates local state if another component changes search params.
 */
export default function ComponentOverviewFilterMenu({
  defaultMaterial,
  defaultCompType,
}: ComponentOverviewFilterMenuProps) {
  const router = useRouter()
  const searchParams = useSearchParams()

  // Local state to store the current filters
  const [material, setMaterial] = useState(defaultMaterial)
  const [compType, setCompType] = useState(defaultCompType)

  // Whenever the searchParams themselves change (due to another component),
  // we sync our local state so our inputs reflect the updated query string.
  useEffect(() => {
    // If the param is missing, we can default to "" or the defaultMaterial
    const newMaterial = searchParams.get('material') || ''
    const newCompType = searchParams.get('comptype') || ''

    setMaterial(newMaterial)
    setCompType(newCompType)
  }, [searchParams])

  function handleApplyFilters() {
    const params = new URLSearchParams(searchParams.toString())
    params.set('material', material)
    params.set('comptype', compType)
    // Optionally reset page to 1
    params.set('page', '1')

    router.replace(`?${params.toString()}`)
  }

  function handleResetFilters() {
    const params = new URLSearchParams(searchParams.toString())
    // Remove or reset these filters from the URL
    params.delete('material')
    params.delete('comptype')
    // Also reset local state, if you want them empty
    setMaterial('')
    setCompType('')
    // Reset page if needed
    params.set('page', '1')

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

      {/* Buttons */}
      <div className="flex items-center gap-2 mt-2">
        <Button onClick={handleApplyFilters}>
          Apply Filters
        </Button>
        <Button variant="secondary" onClick={handleResetFilters}>
          Reset Filters
        </Button>
      </div>
    </Card>
  )
}
