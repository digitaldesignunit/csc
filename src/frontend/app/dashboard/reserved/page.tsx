'use client'

import { useSession } from 'next-auth/react'
import { redirect } from 'next/navigation'
import { useState, useEffect, useCallback } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Bookmark } from 'lucide-react'
import Link from 'next/link'
import { ComponentOverviewDataTable } from '@/components/components/overview/ComponentOverviewDataTable'
import { ComponentOverviewColumns } from '@/components/components/overview/ComponentOverviewColumns'
import { ComponentModel } from '@/generated/ComponentModel'
import { ColumnDef } from '@tanstack/react-table'

// Type for session user with extended properties
interface ExtendedUser {
  id?: string
  sub?: string
  username?: string | null
  name?: string | null
  email?: string | null
}

export default function ReservedComponentsPage() {
  const { data: session, status } = useSession()
  const [reservedComponents, setReservedComponents] = useState<ComponentModel[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create custom columns for reserved components that include the actions column
  const ReservedComponentColumns = ComponentOverviewColumns.filter((col: ColumnDef<ComponentModel>) => 
    (col as ColumnDef<ComponentModel> & { accessorKey?: string }).accessorKey !== 'actions' && 
    (col as ColumnDef<ComponentModel> & { accessorKey?: string }).accessorKey !== 'reserved'
  )
  
  ReservedComponentColumns.push({
    id: 'actions',
    header: () => <div className="text-xs font-semibold text-muted-foreground">Actions</div>,
    meta: { colClassName: 'w-[120px] sm:w-[140px]' },
    cell: ({ row }) => {
      const componentId = row.getValue('_id')
      
      return (
        <div className='text-xs'>
          <button
            onClick={async () => {
              try {
                const response = await fetch(`/api/backend/reserve/${componentId}`, {
                  method: 'DELETE',
                })
                if (response.ok) {
                  // Remove from the list
                  setReservedComponents(prev => prev.filter(comp => comp._id !== componentId))
                } else {
                  const error = await response.json()
                  alert(`Failed to release component: ${error.detail || 'Unknown error'}`)
                }
              } catch (err) {
                console.error('Error releasing component:', err)
                alert('Failed to release component')
              }
            }}
            className='px-2 py-1 text-xs bg-destructive text-destructive-foreground rounded hover:bg-destructive/90 transition-colors cursor-pointer'
          >
            Release
          </button>
        </div>
      )
    },
  })

  const fetchReservedComponents = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      
      // Get the current user's ID from the session
      const extendedUser = session?.user as ExtendedUser
      const userId = extendedUser?.id || extendedUser?.sub || session?.user?.email
      
      if (!userId) {
        setError('Unable to identify user')
        return
      }

      // Fetch reserved components from the API
      const response = await fetch(`/api/backend/reserve/${encodeURIComponent(userId)}`)
      
      if (!response.ok) {
        if (response.status === 404) {
          setReservedComponents([])
          return
        }
        throw new Error(`Failed to fetch reserved components: ${response.status}`)
      }

      const data = await response.json()
      
      if (data.components && Array.isArray(data.components)) {
        setReservedComponents(data.components)
      } else {
        setReservedComponents([])
      }
    } catch (err) {
      console.error('Error fetching reserved components:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch reserved components')
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    if (session?.user) {
      fetchReservedComponents()
    }
  }, [session, fetchReservedComponents])

  if (status === 'loading') {
    return (
      <div className="container mx-auto p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-muted rounded w-1/3"></div>
          <div className="h-64 bg-muted rounded"></div>
        </div>
      </div>
    )
  }

  if (!session?.user) {
    redirect('/auth/signin?callbackUrl=/dashboard/reserved')
  }

  const extendedUser = session.user as ExtendedUser
  const username = extendedUser.username || 
                   session.user.name || 
                   session.user.email || 
                   'User'

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <Bookmark className="h-8 w-8 text-primary" />
            <h1 className="text-2xl sm:text-3xl font-bold">Reserved Components</h1>
          </div>
          <p className="text-muted-foreground text-sm sm:text-base">
            Components reserved by {username}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="text-sm">
            <Bookmark className="h-3 w-3 mr-1" />
            {reservedComponents.length} Reserved
          </Badge>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">{reservedComponents.length}</div>
            <p className="text-xs text-muted-foreground">Total Reserved</p>
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-center">
            <div className="text-lg font-bold">
              {new Set(reservedComponents.map(c => c.type)).size}
            </div>
            <p className="text-xs text-muted-foreground">Component Types</p>
          </div>
        </Card>

        <Card className="p-3">
          <div className="text-center">
            <div className="text-sm font-medium">{username}</div>
            <p className="text-xs text-muted-foreground">Account</p>
          </div>
        </Card>
      </div>

      {/* Help Text */}
      <Card className="bg-muted/30">
        <CardContent>
          <div className="text-sm text-muted-foreground space-y-2">
            <p>
              <strong>How reservations work:</strong> When you reserve a component, it&apos;s marked as reserved. You can release components at any time to make them available again.
            </p>
            <p>
              <strong>Note:</strong> Reserved components are still available and visible in the Catalog but show as 
              reserved to you!
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Main Content */}
      <Card>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          ) : error ? (
            <div className="text-center py-8">
              <p className="text-destructive mb-4">{error}</p>
              <Button onClick={fetchReservedComponents} variant="outline">
                Try Again
              </Button>
            </div>
          ) : reservedComponents.length === 0 ? (
            <div className="text-center py-12">
              <Bookmark className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-foreground mb-2">
                No Reserved Components
              </h3>
              <p className="text-muted-foreground mb-4">
                You haven&apos;t reserved any components yet.
              </p>
              <Link href="/components">
                <Button variant="default">
                  Browse Components
                </Button>
              </Link>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Enhanced columns with release button */}
              <ComponentOverviewDataTable 
                columns={ReservedComponentColumns}
                data={reservedComponents}
              />
              
              {/* Quick Actions */}
              <div className="flex flex-wrap gap-2 pt-4 border-t">
                <Button 
                  variant="outline" 
                  size="sm"
                  onClick={() => window.location.reload()}
                >
                  Refresh List
                </Button>
                <Link href="/components">
                  <Button variant="outline" size="sm">
                    Browse More Components
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      
    </div>
  )
}
