'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DesignComponent, DesignModel } from '@/generated/DesignModel'
import DesignSnapshotPicker from '@/components/designs/DesignSnapshotPicker'
import { toast } from 'sonner'

interface EditDesignPageProps {
  params: Promise<{ design_id: string }>
}

export default function EditDesignPage({ params }: EditDesignPageProps) {
  const router = useRouter()
  const [designId, setDesignId] = useState<string>('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [components, setComponents] = useState<DesignComponent[]>([])
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const loadDesign = async () => {
      const resolvedParams = await params
      const id = resolvedParams.design_id
      setDesignId(id)

      try {
        const response = await fetch(`/api/backend/designs/${id}`)
        if (response.ok) {
          const design: DesignModel = await response.json()
          setName(typeof design.name === 'string' ? design.name : '')
          setDescription(typeof design.description === 'string' ? design.description : '')
          setComponents(design.components || [])
        } else {
          toast.error('Failed to load design')
          router.push('/designs')
        }
      } catch (error) {
        console.error('Error loading design:', error)
        toast.error('Failed to load design')
        router.push('/designs')
      } finally {
        setIsLoading(false)
      }
    }

    void loadDesign()
  }, [params, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (components.length === 0) {
      toast.warning('Please add at least one snapshot placement to the design')
      return
    }

    setIsSubmitting(true)
    try {
      const response = await fetch(`/api/backend/designs/${designId}`, {
        method: 'PATCH',
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
        router.push(`/designs/${designId}`)
      } else {
        const error = await response.text()
        toast.error(`Failed to update design: ${error}`)
      }
    } catch (error) {
      console.error('Error updating design:', error)
      toast.error('Failed to update design')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 m-2 max-w-4xl mx-auto">
        <Card>
          <CardHeader>
            <CardTitle>Loading...</CardTitle>
          </CardHeader>
        </Card>
      </div>
    )
  }

  return (
    <div className="grid gap-4 m-2 max-w-4xl mx-auto">
      <Card>
        <CardHeader>
          <CardTitle>Edit Design</CardTitle>
          <CardDescription>
            Modify snapshot placements in this design assembly
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
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push(`/designs/${designId}`)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting || components.length === 0}>
              {isSubmitting ? 'Updating...' : 'Update Design'}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
