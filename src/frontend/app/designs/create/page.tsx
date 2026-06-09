'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DesignComponent } from '@/generated/DesignModel'
import DesignSnapshotPicker from '@/components/designs/DesignSnapshotPicker'
import { toast } from 'sonner'

export default function CreateDesignPage() {
  const router = useRouter()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [components, setComponents] = useState<DesignComponent[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (components.length === 0) {
      toast.warning('Please add at least one snapshot placement to the design')
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
          components,
        }),
      })

      if (response.ok) {
        const createdDesign = await response.json()
        router.push(`/designs/${createdDesign._id}`)
      } else {
        const error = await response.text()
        toast.error(`Failed to create design: ${error}`)
      }
    } catch (error) {
      console.error('Error creating design:', error)
      toast.error('Failed to create design')
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
            Create a design assembly by placing specific snapshot versions
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
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
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                  setDescription(e.target.value)
                }
                placeholder="Enter design description (optional)"
                rows={3}
              />
            </div>
          </div>

          <DesignSnapshotPicker placements={components} onChange={setComponents} />

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => router.back()}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || components.length === 0}>
              {isSubmitting ? 'Creating...' : 'Create Design'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
