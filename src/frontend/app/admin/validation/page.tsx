'use client'

import { useEffect, useState } from 'react'
import { useSession } from 'next-auth/react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { CheckCircle, Package, Shield, Eye, ChevronDown, ChevronUp, Trash2, ExternalLink } from 'lucide-react'
import { ComponentModel } from '@/generated/ComponentModel'
import ComponentViewer from '@/components/components/ComponentViewer'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

export default function ValidationPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [components, setComponents] = useState<ComponentModel[]>([])
  const [loading, setLoading] = useState(true)
  const [validating, setValidating] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [expandedPreviews, setExpandedPreviews] = useState<Set<string>>(new Set())
  const [componentData, setComponentData] = useState<Record<string, ComponentModel>>({})
  const [loadingPreviews, setLoadingPreviews] = useState<Set<string>>(new Set())

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
      const response = await fetch('/api/backend/shallowcomponents?validated=-1&size=100')
      if (response.ok) {
        const data = await response.json()
        setComponents(data)
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
      const response = await fetch(`/api/backend/validate/${componentId}`, {
        method: 'GET',
      })
      
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
    if (!confirm('Are you sure you want to delete this component? This action cannot be undone.')) {
      return
    }

    try {
      setDeleting(componentId)
      const response = await fetch(`/api/backend/components/${componentId}`, {
        method: 'DELETE',
      })
      
      if (response.ok) {
        // Remove the deleted component from the list
        setComponents(prev => prev.filter(c => c._id !== componentId))
      } else {
        console.error('Failed to delete component')
        alert('Failed to delete component. Please try again.')
      }
    } catch (error) {
      console.error('Error deleting component:', error)
      alert('Failed to delete component. Please try again.')
    } finally {
      setDeleting(null)
    }
  }

  const togglePreview = async (componentId: string) => {
    setExpandedPreviews(prev => {
      const newSet = new Set(prev)
      if (newSet.has(componentId)) {
        newSet.delete(componentId)
        return newSet
      } else {
        newSet.add(componentId)
        return newSet
      }
    })

    // If expanding and we don't have the data yet, fetch it
    if (!expandedPreviews.has(componentId) && !componentData[componentId]) {
      setLoadingPreviews(prev => new Set(prev).add(componentId))
      try {
        const response = await fetch(`/api/backend/components/${componentId}`)
        if (response.ok) {
          const data = await response.json()
          setComponentData(prev => ({ ...prev, [componentId]: data }))
        }
      } catch (error) {
        console.error('Failed to fetch component data:', error)
      } finally {
        setLoadingPreviews(prev => {
          const newSet = new Set(prev)
          newSet.delete(componentId)
          return newSet
        })
      }
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
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <Shield className="h-6 w-6 sm:h-8 sm:w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Validation Dashboard</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          Manage component validation
        </p>
      </div>

      <div className="grid gap-6">
        {/* Component Validation Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Package className="h-5 w-5" />
              Component Validation
            </CardTitle>
            <CardDescription>
              Review and validate pending components before they become publicly available
            </CardDescription>
          </CardHeader>
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
                  <p className="text-sm text-muted-foreground">
                    {components.length} component{components.length !== 1 ? 's' : ''} pending validation
                  </p>
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
                            <p>Created: {new Date(component.created).toLocaleString('de-DE', { 
                              timeZone: 'Europe/Berlin',
                              day: '2-digit',
                              month: '2-digit', 
                              year: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                              second: '2-digit',
                              hour12: false
                            })}</p>
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
                            onClick={() => deleteComponent(component._id!)}
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
                            ) : componentData[component._id!] && component._id ? (
                              <ComponentViewer 
                                component_data={componentData[component._id]}
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

        {/* Admin Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Pending Validation
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{components.length}</div>
              <p className="text-xs text-muted-foreground">
                Components awaiting review
              </p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total Components
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">-</div>
              <p className="text-xs text-muted-foreground">
                All components in system
              </p>
            </CardContent>
          </Card>
          
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Validated Today
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">-</div>
              <p className="text-xs text-muted-foreground">
                Components validated today
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
