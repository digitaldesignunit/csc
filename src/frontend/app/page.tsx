'use client'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import Link from 'next/link'
import { useSession } from 'next-auth/react'
import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Package, BookOpen, Users, Settings } from 'lucide-react'

export default function Home() {
  const { data: session, status } = useSession()

  return (
    <div className="container mx-auto p-6 space-y-6 max-w-6xl">
      {/* Header */}
      <div className="mb-6 sm:mb-8">
        <div className="flex items-center gap-2 sm:gap-3 mb-2">
          <BookOpen className="h-8 w-8 text-primary" />
          <h1 className="text-2xl sm:text-3xl font-bold">Catalogue of Second Chances</h1>
        </div>
        <p className="text-muted-foreground text-sm sm:text-base">
          A repository for architectural component reuse
        </p>
      </div>

      {/* Background Mesh */}
      <BackgroundMesh
          className="absolute inset-0 -z-10"
          opacity={0.08}
          rotationSpeed={0.15}
          intensity={0.2}
        />

      {/* Main Content */}
      <div className="relative z-10 space-y-6">
        
        {/* About Section */}
        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5" />
              About
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <p>
              The <i>Catalogue of Second Chances</i> is a digital repository designed to store and make accessible digitized representations of building components. 
              It supports practices of reuse and circularity in architecture by providing structured access to component data.
            </p>
            <p>
              The catalogue can be accessed in two ways: through this web interface, and from within the parametric design environment 
              <i> Rhino/Grasshopper</i> using custom Python components. It is primarily developed for use in architectural research and teaching, 
              where it serves as a testbed for workflows involving reuse, digital documentation, and component-based design.
            </p>
            <p>
              The aim is not only to facilitate browsing and retrieval of components, but also to support experimental approaches to cataloguing, 
              data modeling, and digital reuse practices in architectural contexts.
            </p>
          </CardContent>
        </Card>

        {/* Access Section - Only show when user is not logged in */}
        {status !== 'loading' && !session?.user && (
          <Card className="bg-card/75">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Access
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-base leading-relaxed">
              <p>
                To browse components and interact with the repository, you need to create an account and log in. 
                Registered users can explore the catalogue, access component data, and begin working with it either 
                through the web interface or within Rhino/Grasshopper.
              </p>
              <div className="flex gap-4">
                <Link href="/auth/signin">
                  <Button variant="default">Sign In</Button>
                </Link>
                <Link href="/auth/register">
                  <Button variant="outline">Register</Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Quick Actions - Only show when user is logged in */}
        {status !== 'loading' && session?.user && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Quick Actions
              </CardTitle>
              <CardDescription>
                Get started with the catalogue
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <Link href="/components">
                  <Button variant="outline" className="w-full h-auto p-4 flex flex-col items-center gap-2">
                    <Package className="h-6 w-6" />
                    <span className="font-medium">Browse Components</span>
                    <span className="text-xs">Explore the component catalogue</span>
                  </Button>
                </Link>
                <Link href="/designs">
                  <Button variant="outline" className="w-full h-auto p-4 flex flex-col items-center gap-2">
                    <BookOpen className="h-6 w-6" />
                    <span className="font-medium">View Designs</span>
                    <span className="text-xs">Browse design collections</span>
                  </Button>
                </Link>
                <Link href="/dashboard">
                  <Button variant="outline" className="w-full h-auto p-4 flex flex-col items-center gap-2">
                    <Users className="h-6 w-6" />
                    <span className="font-medium">Dashboard</span>
                    <span className="text-xs">Your personal workspace</span>
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}
