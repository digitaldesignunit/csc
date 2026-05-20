'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, Shield, Eye, ChevronDown, ChevronUp, Trash2, ExternalLink } from 'lucide-react'
import { ComponentModel } from '@/generated/ComponentModel'
import type { CatalogComponent } from '@/generated/CatalogModels'
import ComponentViewer from '@/components/components/ComponentViewer'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatTimestamp } from '@/lib/utils'
import { toast } from 'sonner'

export default function ValidationPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [components, setComponents] = useState<ComponentModel[]>([])
  const [loading, setLoading] = useState(true)
  const [validating, setValidating] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [expandedPreviews, setExpandedPreviews] = useState<Set<string>>(new Set())
  const [previewById, setPreviewById] = useState<Record<string, CatalogComponent>>({})
  const [loadingPreviews, setLoadingPreviews] = useState<Set<string>>(new Set())
  const [deleteConfirmComponentId, setDeleteConfirmComponentId] = useState<string | null>(null)

  // Redirect non-admin users or expired sessions
  useEffect(() => {
    if (status === 'loading') return
    
    if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
      router.push('/')
    }
  }, [session, status, router])

  // Fetch unvalidated components
  useEffect(() => {
    if (session?.user?.role === 'admin' && !session.error) {
      fetchUnvalidatedComponents()
    }
  }, [session])

  const fetchUnvalidatedComponents = async () => {
    try {
      setLoading(true)
      const response = await fetch(
        '/api/backend/identities?validated=-1&size=100&expand=shallow',
        { credentials: 'include' },
      )
      if (response.ok) {
        const data = await response.json()
        // Sort by created date (newest first)
        const sortedByCreated = [...data].sort((a: ComponentModel, b: ComponentModel) => {
          const aTime = a?.created ? new Date(a.created as unknown as string).getTime() : 0
          const bTime = b?.created ? new Date(b.created as unknown as string).getTime() : 0
          return bTime - aTime
        })
        setComponents(sortedByCreated)
      }
    } catch (error) {
      console.error('Failed to fetch components:', error)
    } finally {
      setLoading(false)
    }
  }

  const validateComponent = async (componentId: string) => {
    try {
      setValidating(componentId)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(componentId)}/validate`,
        { method: 'GET', credentials: 'include' },
      )
      
      if (response.ok) {
        // Remove the validated component from the list
        setComponents(prev => prev.filter(c => c._id !== componentId))
      } else {
        console.error('Failed to validate component')
      }
    } catch (error) {
      console.error('Error validating component:', error)
    } finally {
      setValidating(null)
    }
  }

  const deleteComponent = async (componentId: string) => {
    try {
      setDeleting(componentId)
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(componentId)}`,
        {
          method: 'DELETE',
          credentials: 'include',
        },
      )
      
      if (response.ok) {
        // Remove the deleted component from the list
        setComponents(prev => prev.filter(c => c._id !== componentId))
      } else {
        console.error('Failed to delete component')
        toast.error('Failed to delete component. Please try again.')
      }
    } catch (error) {
      console.error('Error deleting component:', error)
      toast.error('Failed to delete component. Please try again.')
    } finally {
      setDeleting(null)
    }
  }

  const confirmDeleteComponent = async () => {
    const componentId = deleteConfirmComponentId
    if (!componentId) return
    setDeleteConfirmComponentId(null)
    await deleteComponent(componentId)
  }

  const fetchComposePreview = async (identityId: string) => {
    setLoadingPreviews((prev) => new Set(prev).add(identityId))
    try {
      const response = await fetch(
        `/api/backend/identities/${encodeURIComponent(identityId)}/compose`,
        { credentials: 'include', cache: 'no-store' },
      )
      if (response.ok) {
        const json = (await response.json()) as CatalogComponent
        setPreviewById((prev) => ({
          ...prev,
          [identityId]: json,
        }))
      }
    } catch (error) {
      console.error('Failed to fetch compose for preview:', error)
    } finally {
      setLoadingPreviews((prev) => {
        const next = new Set(prev)
        next.delete(identityId)
        return next
      })
    }
  }

  const togglePreview = (componentId: string) => {
    const wasExpanded = expandedPreviews.has(componentId)
    setExpandedPreviews((prev) => {
      const next = new Set(prev)
      if (wasExpanded) {
        next.delete(componentId)
      } else {
        next.add(componentId)
      }
      return next
    })

    if (!wasExpanded && !previewById[componentId]) {
      void fetchComposePreview(componentId)
    }
  }

  if (status === 'loading') {
    return (
      <div className="container mx-auto p-6">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </div>
    )
  }

  if (!session?.user || session.user.role !== 'admin' || session.error === 'ApiTokenExpired') {
    return null // Will redirect
  }

  return (
    <div className="container mx-auto p-4 sm:p-6">
      <div className="mb-4 sm:mb-6">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Shield className="h-5 w-5 sm:h-6 sm:w-6 text-primary" />
          <h1 className="text-xl sm:text-2xl font-bold">Validation Dashboard</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          Review and validate pending components before they become publicly available
        </p>
      </div>

      {/* Admin Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">{components.length}</div>
            <p className="text-xs text-muted-foreground">Pending Validation</p>
          </div>
        </Card>
        
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">-</div>
            <p className="text-xs text-muted-foreground">Total Components</p>
          </div>
        </Card>
        
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">-</div>
            <p className="text-xs text-muted-foreground">Validated Today</p>
          </div>
        </Card>
      </div>

      <div className="grid gap-6">
        {/* Component Validation Section */}
        <Card>
          {/* <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Package className="h-5 w-5" />
              Component Validation
            </CardTitle>
            <CardDescription>
              Review and validate pending components before they become publicly available
            </CardDescription>
          </CardHeader> */}
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary"></div>
              </div>
            ) : components.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <CheckCircle className="h-12 w-12 mx-auto mb-4 text-green-500" />
                <p className="text-lg font-medium">All components are validated!</p>
                <p>No pending components require validation.</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                  <Button
                    onClick={fetchUnvalidatedComponents}
                    variant="outline"
                    size="sm"
                    className="w-full sm:w-auto"
                  >
                    Refresh
                  </Button>
                </div>
                
                <div className="grid gap-4">
                  {components.map((component) => (
                    <div
                      key={component._id}
                      className="border rounded-lg hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between p-4 gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <h3 className="font-medium text-sm sm:text-base truncate">
                              {(typeof component.name === 'string' && component.name) || (
                                <Link 
                                  href={`/components/${component._id}`}
                                  className="text-primary hover:text-primary/80 hover:underline inline-flex items-center gap-1 transition-colors"
                                >
                                  Component {component._id?.slice(0, 8)}
                                  <ExternalLink className="h-3 w-3" />
                                </Link>
                              )}
                            </h3>
                          </div>
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            <Badge variant="secondary" className="text-xs">{component.type}</Badge>
                              <Badge variant="outline" className="text-xs">{component.material}</Badge>
                              {component.complexity !== undefined && 
                              component.complexity !== null && 
                              typeof component.complexity === 'number' && (
                                <Badge variant="outline" className="text-xs">Complexity: {component.complexity}</Badge>
                              )}
                          </div>
                          <div className="text-xs sm:text-sm text-muted-foreground space-y-1">
                            <p className="break-all">
                              ID: <Link 
                                href={`/components/${component._id}`}
                                className="text-primary hover:text-primary/80 hover:underline inline-flex items-center gap-1 transition-colors"
                              >
                                {component._id}
                                <ExternalLink className="h-3 w-3" />
                              </Link>
                            </p>
                            <p>Created: {formatTimestamp(component.created)}</p>
                            <p>Fragment: {component.fragment ? 'Yes' : 'No'}</p>
                            <p>Assembly: {component.assembly ? 'Yes' : 'No'}</p>
                          </div>
                        </div>
                        
                        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 lg:ml-4 lg:flex-shrink-0">
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  onClick={() => togglePreview(component._id!)}
                                  variant="outline"
                                  size="sm"
                                  className="flex items-center gap-2 w-full sm:w-auto"
                                >
                                  {loadingPreviews.has(component._id!) ? (
                                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-current"></div>
                                  ) : (
                                    <Eye className="h-4 w-4" />
                                  )}
                                  {expandedPreviews.has(component._id!) ? (
                                    <>
                                      <ChevronUp className="h-4 w-4" />
                                      <span className="hidden sm:inline">Hide</span>
                                    </>
                                  ) : (
                                    <>
                                      <ChevronDown className="h-4 w-4" />
                                      <span className="hidden sm:inline">Preview</span>
                                    </>
                                  )}
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Preview 3D geometry and component details</p>
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                          <Button
                            onClick={() => validateComponent(component._id!)}
                            disabled={validating === component._id || deleting === component._id}
                            size="sm"
                            className="bg-green-600 hover:bg-green-700 w-full sm:w-auto"
                          >
                            {validating === component._id ? (
                              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                            ) : (
                              <>
                                <CheckCircle className="h-4 w-4 sm:mr-2" />
                                <span className="hidden sm:inline">Validate</span>
                              </>
                            )}
                          </Button>
                          <Button
                            onClick={() => setDeleteConfirmComponentId(component._id!)}
                            disabled={validating === component._id || deleting === component._id}
                            size="sm"
                            variant="destructive"
                            className="w-full sm:w-auto"
                          >
                            {deleting === component._id ? (
                              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                            ) : (
                              <>
                                <Trash2 className="h-4 w-4 sm:mr-2" />
                                <span className="hidden sm:inline">Delete</span>
                              </>
                            )}
                          </Button>
                        </div>
                      </div>
                      
                      {/* Expandable Preview Section */}
                      {expandedPreviews.has(component._id!) && (
                        <div className="p-3 sm:p-4 bg-muted/30 rounded-b-lg border-t">
                          <div className="mb-3">
                            <h4 className="text-sm font-medium text-muted-foreground mb-2">
                              Component Preview - {(typeof component.name === 'string' && component.name) || (
                                <Link 
                                  href={`/components/${component._id}`}
                                  className="text-primary hover:text-primary/80 hover:underline inline-flex items-center gap-1 transition-colors"
                                >
                                  Component {component._id?.slice(0, 8)}
                                  <ExternalLink className="h-3 w-3" />
                                </Link>
                              )}
                            </h4>
                            <p className="text-xs text-muted-foreground">
                              Interactive 3D view with orbit controls. Use mouse to rotate, scroll to zoom.
                            </p>
                          </div>
                          <div className="h-full w-full">
                            {loadingPreviews.has(component._id!) ? (
                              <div className="flex items-center justify-center h-full">
                                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                              </div>
                            ) : previewById[component._id!] && component._id ? (
                              <ComponentViewer
                                catalog={previewById[component._id]}
                              />
                            ) : (
                              <div className="flex items-center justify-center h-full text-muted-foreground">
                                Failed to load component data
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

      </div>
      <Dialog
        open={Boolean(deleteConfirmComponentId)}
        onOpenChange={(open) => {
          if (!open) setDeleteConfirmComponentId(null)
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Permanently delete component?</DialogTitle>
            <DialogDescription>
              This action cannot be undone. The component and associated files will be permanently removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmComponentId(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={confirmDeleteComponent}
              disabled={!deleteConfirmComponentId || deleting === deleteConfirmComponentId}
            >
              Confirm Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
