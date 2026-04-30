'use client'

import { useState, useEffect } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion'
import { Filter } from 'lucide-react'

interface ComponentOverviewFilterMenuProps {
  defaultMaterial: string
  defaultCompType: string
  defaultDataset: string
  defaultPageSize?: number
  /** Optional custom endpoint for fetching materials (default: '/api/backend/materials') */
  materialsEndpoint?: string
  /** Optional custom endpoint for fetching component types (default: '/api/backend/componenttypes') */
  componentTypesEndpoint?: string
  /** Optional custom endpoint for fetching datasets (default: '/api/backend/datasets') */
  datasetsEndpoint?: string
}

/**
 * A client component that displays a collapsible filter form
 * for all component attributes. When the user clicks "Apply",
 * it updates the search params in the URL, causing the server component
 * (page.tsx) to re-fetch with new filters.
 *
 * - Has a "Reset" button to clear all filters.
 * - Automatically updates local state if another component changes search params.
 * - Collapsible design for better space management.
 */
export default function ComponentOverviewFilterMenu({
  defaultMaterial,
  defaultCompType,
  defaultDataset,
  defaultPageSize = 20,
  materialsEndpoint = '/api/backend/materials',
  componentTypesEndpoint = '/api/backend/componenttypes',
  datasetsEndpoint = '/api/backend/datasets',
}: ComponentOverviewFilterMenuProps) {
  const router = useRouter()
  const searchParams = useSearchParams()

  // Local state to store all the current filters
  const [material, setMaterial] = useState(defaultMaterial)
  const [compType, setCompType] = useState(defaultCompType)
  const [dataset, setDataset] = useState(defaultDataset)
  const [complexity, setComplexity] = useState('')
  const [fragment, setFragment] = useState('')
  const [bbxMinX, setBbxMinX] = useState('')
  const [bbxMinY, setBbxMinY] = useState('')
  const [bbxMinZ, setBbxMinZ] = useState('')
  const [bbxMaxX, setBbxMaxX] = useState('')
  const [bbxMaxY, setBbxMaxY] = useState('')
  const [bbxMaxZ, setBbxMaxZ] = useState('')
  const [pageSize, setPageSize] = useState(String(defaultPageSize))
  
  // State for available materials and component types
  const [availableMaterials, setAvailableMaterials] = useState<string[]>([])
  const [availableComponentTypes, setAvailableComponentTypes] = useState<string[]>([])

  // State for available datasets
  const [availableDatasets, setAvailableDatasets] = useState<string[]>([])

  // Count active filters for badge display
  const activeFiltersCount = [
    material, compType, dataset, complexity, fragment,
    bbxMinX, bbxMinY, bbxMinZ, bbxMaxX, bbxMaxY, bbxMaxZ
  ].filter(Boolean).length

  // Fetch available filter options on component mount
  useEffect(() => {
    const fetchFilterOptions = async () => {
      try {
        const [materialsResponse, componentTypesResponse, datasetsResponse] = await Promise.all([
          fetch(materialsEndpoint),
          fetch(componentTypesEndpoint),
          fetch(datasetsEndpoint),
        ])

        if (materialsResponse.ok) {
          const materials = await materialsResponse.json()
          setAvailableMaterials(materials)
        }
        if (componentTypesResponse.ok) {
          const types = await componentTypesResponse.json()
          setAvailableComponentTypes(types)
        }
        if (datasetsResponse.ok) {
          const datasets = await datasetsResponse.json()
          setAvailableDatasets(datasets)
        }
      } catch (error) {
        console.error('Failed to fetch filter options:', error)
      }
    }
    fetchFilterOptions()
  }, [materialsEndpoint, componentTypesEndpoint, datasetsEndpoint])

  // Whenever the searchParams themselves change (due to another component),
  // we sync our local state so our inputs reflect the updated query string.
  useEffect(() => {
    const newMaterial = searchParams.get('material') || ''
    const newCompType = searchParams.get('comptype') || ''
    const newDataset = searchParams.get('dataset') || ''
    const newComplexity = searchParams.get('complexity') || ''
    const newFragment = searchParams.get('fragment') || ''
    const newBbxMinX = searchParams.get('bbx_min_x') || ''
    const newBbxMinY = searchParams.get('bbx_min_y') || ''
    const newBbxMinZ = searchParams.get('bbx_min_z') || ''
    const newBbxMaxX = searchParams.get('bbx_max_x') || ''
    const newBbxMaxY = searchParams.get('bbx_max_y') || ''
    const newBbxMaxZ = searchParams.get('bbx_max_z') || ''
    const newPageSize = searchParams.get('size') || String(defaultPageSize)

    setMaterial(newMaterial)
    setCompType(newCompType)
    setDataset(newDataset)
    setComplexity(newComplexity)
    setFragment(newFragment)
    setBbxMinX(newBbxMinX)
    setBbxMinY(newBbxMinY)
    setBbxMinZ(newBbxMinZ)
    setBbxMaxX(newBbxMaxX)
    setBbxMaxY(newBbxMaxY)
    setBbxMaxZ(newBbxMaxZ)
    setPageSize(newPageSize)
  }, [searchParams, defaultPageSize])

  function handleApplyFilters() {
    const params = new URLSearchParams(searchParams.toString())

    const applyFilterParam = (key: string, value: string) => {
      const normalizedValue = value.trim()
      if (normalizedValue) {
        params.set(key, normalizedValue)
        return
      }
      params.delete(key)
    }

    // Keep URL filter params in sync with local state, including cleared fields.
    applyFilterParam('material', material)
    applyFilterParam('comptype', compType)
    applyFilterParam('dataset', dataset)
    applyFilterParam('complexity', complexity)
    applyFilterParam('fragment', fragment)
    applyFilterParam('bbx_min_x', bbxMinX)
    applyFilterParam('bbx_min_y', bbxMinY)
    applyFilterParam('bbx_min_z', bbxMinZ)
    applyFilterParam('bbx_max_x', bbxMaxX)
    applyFilterParam('bbx_max_y', bbxMaxY)
    applyFilterParam('bbx_max_z', bbxMaxZ)
    applyFilterParam('size', pageSize)
    
    // Reset page to 1 when applying filters
    params.set('page', '1')

    router.replace(`?${params.toString()}`)
  }

  function handleResetFilters() {
    const params = new URLSearchParams(searchParams.toString())
    
    // Remove all filter parameters from the URL
    params.delete('material')
    params.delete('comptype')
    params.delete('dataset')
    params.delete('complexity')
    params.delete('fragment')
    params.delete('bbx_min_x')
    params.delete('bbx_min_y')
    params.delete('bbx_min_z')
    params.delete('bbx_max_x')
    params.delete('bbx_max_y')
    params.delete('bbx_max_z')
    params.delete('size')
    
    // Reset local state
    setMaterial('')
    setCompType('')
    setDataset('')
    setComplexity('')
    setFragment('')
    setBbxMinX('')
    setBbxMinY('')
    setBbxMinZ('')
    setBbxMaxX('')
    setBbxMaxY('')
    setBbxMaxZ('')
    setPageSize(String(defaultPageSize))
    
    // Reset page to 1
    params.set('page', '1')

    router.replace(`?${params.toString()}`)
  }

  return (
    <Card className="p-3">
      <Accordion type="single" collapsible>
        <AccordionItem value="filters" className="border-none">
          <AccordionTrigger className="hover:no-underline py-2">
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4" />
              <span className="font-medium">Filters &amp; Settings</span>
              {activeFiltersCount > 0 && (
                <span className="bg-primary text-primary-foreground text-xs px-2 py-1 rounded-full">
                  {activeFiltersCount}
                </span>
              )}
            </div>
          </AccordionTrigger>
          <AccordionContent>
            <div className="space-y-4 pt-2">
              {/* Basic Filters Row */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="materialInput" className="text-sm font-medium">Material</Label>
                  <select
                    id="materialInput"
                    value={material}
                    onChange={(e) => setMaterial(e.target.value)}
                    className="h-8 px-3 py-1 text-sm border border-input rounded-md bg-background"
                  >
                    <option value="">Any material</option>
                    {availableMaterials.length > 0 ? (
                      availableMaterials.map((mat) => (
                        <option key={mat} value={mat}>{mat}</option>
                      ))
                    ) : (
                      <option value="" disabled>Loading materials...</option>
                    )}
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="comptypeInput" className="text-sm font-medium">Component Type</Label>
                  <select
                    id="comptypeInput"
                    value={compType}
                    onChange={(e) => setCompType(e.target.value)}
                    className="h-8 px-3 py-1 text-sm border border-input rounded-md bg-background"
                  >
                    <option value="">Any type</option>
                    {availableComponentTypes.length > 0 ? (
                      availableComponentTypes.map((type) => (
                        <option key={type} value={type}>{type}</option>
                      ))
                    ) : (
                      <option value="" disabled>Loading types...</option>
                    )}
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="datasetInput" className="text-sm font-medium">Dataset</Label>
                  <select
                    id="datasetInput"
                    value={dataset}
                    onChange={(e) => setDataset(e.target.value)}
                    className="h-8 px-3 py-1 text-sm border border-input rounded-md bg-background"
                  >
                    <option value="">Any dataset</option>
                    {availableDatasets.length > 0 ? (
                      availableDatasets.map((ds) => (
                        <option key={ds} value={ds}>{ds}</option>
                      ))
                    ) : (
                      <option value="" disabled>Loading datasets...</option>
                    )}
                  </select>
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="complexityInput" className="text-sm font-medium">Complexity</Label>
                  <select
                    id="complexityInput"
                    value={complexity}
                    onChange={(e) => setComplexity(e.target.value)}
                    className="h-8 px-3 py-1 text-sm border border-input rounded-md bg-background"
                  >
                    <option value="">Any complexity</option>
                    <option value="0">0 - Simplest</option>
                    <option value="1">1 - Simple</option>
                    <option value="2">2 - Medium</option>
                    <option value="3">3 - Complex</option>
                  </select>
                </div>
              </div>

              {/* Fragment + Settings Row */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="flex flex-col gap-2">
                  <Label htmlFor="fragmentInput" className="text-sm font-medium">Fragment Status</Label>
                  <select
                    id="fragmentInput"
                    value={fragment}
                    onChange={(e) => setFragment(e.target.value)}
                    className="h-8 px-3 py-1 text-sm border border-input rounded-md bg-background"
                  >
                    <option value="">Any fragment status</option>
                    <option value="true">Fragment only</option>
                    <option value="false">Non-fragment only</option>
                  </select>
                </div>
                <div className="flex flex-col gap-2">
                  <Label htmlFor="pageSizeInput" className="text-sm font-medium">Rows per page</Label>
                  <select
                    id="pageSizeInput"
                    value={pageSize}
                    onChange={(e) => setPageSize(e.target.value)}
                    className="h-8 px-3 py-1 text-sm border border-input rounded-md bg-background"
                  >
                    <option value="10">10</option>
                    <option value="20">20</option>
                    <option value="50">50</option>
                    <option value="100">100</option>
                  </select>
                </div>
              </div>

              {/* Bounding Box Filters */}
              <div className="space-y-3">
                <Label className="text-sm font-medium">Bounding Box Dimensions</Label>
                <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
                  <div className="flex flex-col gap-2">
                    <Label className="text-xs text-muted-foreground">Min X</Label>
                    <Input
                      placeholder="Min X"
                      value={bbxMinX}
                      onChange={(e) => setBbxMinX(e.target.value)}
                      className="h-8"
                      type="number"
                      step="0.1"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-xs text-muted-foreground">Max X</Label>
                    <Input
                      placeholder="Max X"
                      value={bbxMaxX}
                      onChange={(e) => setBbxMaxX(e.target.value)}
                      className="h-8"
                      type="number"
                      step="0.1"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-xs text-muted-foreground">Min Y</Label>
                    <Input
                      placeholder="Min Y"
                      value={bbxMinY}
                      onChange={(e) => setBbxMinY(e.target.value)}
                      className="h-8"
                      type="number"
                      step="0.1"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-xs text-muted-foreground">Max Y</Label>
                    <Input
                      placeholder="Max Y"
                      value={bbxMaxY}
                      onChange={(e) => setBbxMaxY(e.target.value)}
                      className="h-8"
                      type="number"
                      step="0.1"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-xs text-muted-foreground">Min Z</Label>
                    <Input
                      placeholder="Min Z"
                      value={bbxMinZ}
                      onChange={(e) => setBbxMinZ(e.target.value)}
                      className="h-8"
                      type="number"
                      step="0.1"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label className="text-xs text-muted-foreground">Max Z</Label>
                    <Input
                      placeholder="Max Z"
                      value={bbxMaxZ}
                      onChange={(e) => setBbxMaxZ(e.target.value)}
                      className="h-8"
                      type="number"
                      step="0.1"
                    />
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2 pt-2">
                <Button onClick={handleApplyFilters} size="sm">
                  Apply
                </Button>
                <Button variant="secondary" onClick={handleResetFilters} size="sm">
                  Reset All
                </Button>
                {activeFiltersCount > 0 && (
                  <span className="text-xs text-muted-foreground ml-2">
                    {activeFiltersCount} active filter{activeFiltersCount !== 1 ? 's' : ''}
                  </span>
                )}
              </div>
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </Card>
  )
}
