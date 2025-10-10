'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DesignComponent } from '@/generated/DesignModel'
import { ComponentModel } from '@/generated/ComponentModel'
import { Plus, X, Search } from 'lucide-react'

export default function CreateDesignPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [components, setComponents] = useState<DesignComponent[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<ComponentModel[]>([])
  const [isSearching, setIsSearching] = useState(false)

  const handleSearch = async () => {
    if (!searchQuery.trim()) return
    
    setIsSearching(true)
    try {
      const response = await fetch(`/api/backend/shallowcomponents?page=1&size=20&comptype=&material=&dataset=`)
      if (response.ok) {
        const data = await response.json()
        setSearchResults(data)
      }
    } catch (error) {
      console.error('Search failed:', error)
    } finally {
      setIsSearching(false)
    }
  }

  const addComponent = (component: ComponentModel) => {
    const newComponent: DesignComponent = {
      component: component._id || '',
      iframe: {
        o: [0, 0, 0],
        x: [1, 0, 0],
        y: [0, 1, 0],
        z: [0, 0, 1]
      }
    }
    setComponents(prev => [...prev, newComponent])
    setSearchQuery('')
    setSearchResults([])
  }

  const removeComponent = (index: number) => {
    setComponents(prev => prev.filter((_, i) => i !== index))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (components.length === 0) {
      alert('Please add at least one component to the design')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await fetch('/api/backend/designs', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: name || undefined,
          description: description || undefined,
          components
        })
      })

      if (response.ok) {
        const createdDesign = await response.json()
        router.push(`/designs/${createdDesign._id || createdDesign.id}`)
      } else {
        const error = await response.text()
        alert(`Failed to create design: ${error}`)
      }
    } catch (error) {
      console.error('Error creating design:', error)
      alert('Failed to create design')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="grid gap-4 m-2 max-w-4xl mx-auto">
      <Card>
        <CardHeader>
          <CardTitle>Create New Design</CardTitle>
          <CardDescription>
            Create a new design assembly by combining existing components
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Basic Information */}
          <div className="space-y-4">
            <div>
              <Label htmlFor="name">Design Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter design name (optional)"
              />
            </div>
            <div>
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDescription(e.target.value)}
                placeholder="Enter design description (optional)"
                rows={3}
              />
            </div>
          </div>

          {/* Component Search */}
          <div className="space-y-4">
            <div>
              <Label htmlFor="search">Add Components</Label>
              <div className="flex gap-2">
                <Input
                  id="search"
                  value={searchQuery}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearchQuery(e.target.value)}
                  placeholder="Search for components..."
                  onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && (e.preventDefault(), handleSearch())}
                />
                <Button type="button" onClick={handleSearch} disabled={isSearching}>
                  <Search className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Search Results */}
            {searchResults.length > 0 && (
              <div className="border rounded-lg p-4 max-h-48 overflow-y-auto">
                <h4 className="font-medium mb-2">Search Results</h4>
                <div className="space-y-2">
                  {searchResults.map((component) => (
                    <div key={component._id} className="flex items-center justify-between p-2 border rounded">
                      <div>
                        <div className="font-medium">{String(component.name) || 'Unnamed Component'}</div>
                        <div className="text-sm text-muted-foreground">
                          {component.type} • {component.material}
                        </div>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => addComponent(component)}
                      >
                        <Plus className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Selected Components */}
          <div className="space-y-4">
            <Label>Selected Components ({components.length})</Label>
            {components.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No components added yet. Search and add components above.
              </div>
            ) : (
              <div className="space-y-2">
                {components.map((comp, index) => (
                  <div key={index} className="flex items-center justify-between p-3 border rounded-lg">
                    <div>
                      <div className="font-medium">Component {comp.component.slice(0, 8)}...</div>
                      <div className="text-sm text-muted-foreground">
                        Position: [{comp.iframe.o.map(v => v.toFixed(2)).join(', ')}]
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => removeComponent(index)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Submit */}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.back()}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting || components.length === 0}
            >
              {isSubmitting ? 'Creating...' : 'Create Design'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
