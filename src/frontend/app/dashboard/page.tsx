'use client'

import { useSession } from 'next-auth/react'
import { redirect } from 'next/navigation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { 
  User,
  Settings,
  Search,
  Bookmark,
  Calendar
} from 'lucide-react'
import Link from 'next/link'

export default function DashboardPage() {
  const { data: session, status } = useSession()

  if (status === 'loading') {
    return (
      <div className="container mx-auto p-6">
        <div className="animate-pulse space-y-6">
          <div className="h-8 bg-muted rounded w-1/3"></div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-32 bg-muted rounded"></div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (!session?.user) {
    redirect('/auth/signin?callbackUrl=/dashboard')
  }

  const username = (session.user as { username?: string | null }).username || 
                   session.user.name || 
                   session.user.email || 
                   'User'

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <User className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">User Dashboard</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
        Welcome back, {username}! Manage your account and view your activities.
        </p>
      </div>

      {/* Quick Stats */}
      {/* TODO: Add quick stats */}
      {/*
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Components</CardTitle>
            <Package className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">-</div>
            <p className="text-xs text-muted-foreground">
              Available in Catalog
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Reserved</CardTitle>
            <Bookmark className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">-</div>
            <p className="text-xs text-muted-foreground">
              Your reservations
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Last Activity</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">-</div>
            <p className="text-xs text-muted-foreground">
              Recent activity
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Account Status</CardTitle>
            <User className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <Badge variant="secondary" className="text-xs">
              Active
            </Badge>
            <p className="text-xs text-muted-foreground mt-1">
              Account verified
            </p>
          </CardContent>
        </Card>
      </div>
      */}

      {/* Main Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {/* Reserved Components */}
        <Card className="hover:shadow-lg transition-shadow flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bookmark className="h-5 w-5 text-primary" />
              Reserved Components
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1">
            <p className="text-sm text-muted-foreground">
              View and manage all components you have reserved for your projects.
            </p>
            <div className="mt-auto pt-4">
              <Link href="/dashboard/reserved">
                <Button className="w-full" variant="default">
                  View Reserved Components
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Component Search */}
        <Card className="hover:shadow-lg transition-shadow flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5 text-primary" />
              Find Components
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1">
            <p className="text-sm text-muted-foreground">
              Search and browse the component Catalog to find what you need.
            </p>
            <div className="mt-auto pt-4">
              <Link href="/components">
                <Button className="w-full" variant="outline">
                  Browse Catalog
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Locate by ID */}
        <Card className="hover:shadow-lg transition-shadow flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Search className="h-5 w-5 text-primary" />
              Locate by ID
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1">
            <p className="text-sm text-muted-foreground">
              Locate a physical component based on its <b>Component ID</b>.
            </p>
            <div className="mt-auto pt-4">
              <Link href="/locate-by-id">
                <Button className="w-full" variant="outline">
                  Locate by ID
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Account Settings */}
        <Card className="hover:shadow-lg transition-shadow flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5 text-primary" />
              Account Settings
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1">
            <p className="text-sm text-muted-foreground">
              Manage your account preferences and profile information.
            </p>
            <div className="mt-auto pt-4">
              <Link href="/settings">
                <Button className="w-full" variant="outline">
                  Manage Account
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card className="hover:shadow-lg transition-shadow flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calendar className="h-5 w-5 text-primary" />
              Recent Activity
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1">
            <p className="text-sm text-muted-foreground">
              View your recent component interactions and reservations.
            </p>
            <div className="mt-auto pt-4">
              <Button className="w-full" variant="outline" disabled>
                Coming Soon
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Help & Support */}
        <Card className="hover:shadow-lg transition-shadow flex flex-col">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <User className="h-5 w-5 text-primary" />
              Help & Support
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col flex-1">
            <p className="text-sm text-muted-foreground">
              Get help with using the system or report issues.
            </p>
            <div className="mt-auto pt-4">
              <Link href={`mailto:eschenbach@dg.tu-darmstadt.de?subject=[CSC]%20Support%20Request%20by%20user%20'${username}'&body=Please%20describe%20the%20issue%20you%20are%20facing%20in%20detail.%20Include%20any%20error%20messages%20or%20logs%20you%20have%20received.`}>
                <Button className="w-full" variant="outline">
                  Get Help!
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Quick Links */}
      <Card>
        <CardHeader>
          <CardTitle>Quick Links</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Link href="/components">
              <Badge variant="outline" className="cursor-pointer hover:bg-primary hover:text-primary-foreground">
                Browse Components
              </Badge>
            </Link>
            <Link href="/dashboard/reserved">
              <Badge variant="outline" className="cursor-pointer hover:bg-primary hover:text-primary-foreground">
                My Reservations
              </Badge>
            </Link>
            <Link href="/locate-by-id">
              <Badge variant="outline" className="cursor-pointer hover:bg-primary hover:text-primary-foreground">
                Locate by ID
              </Badge>
            </Link>
            <Link href="/settings">
              <Badge variant="outline" className="cursor-pointer hover:bg-primary hover:text-primary-foreground">
                Settings
              </Badge>
            </Link>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
