'use client'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import Link from 'next/link'
import { useSession } from 'next-auth/react'

export default function Home() {
  const { data: session, status } = useSession()

  return (
    <div className='grid gap-[32px] m-4'>
      <Card>
        <CardHeader>
          <CardTitle>Catalogue of Second Chances</CardTitle>
          <CardDescription>
            A repository for architectural component reuse
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4 text-sm leading-relaxed">
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

      {/* Only show Access card when user is not logged in */}
      {status !== 'loading' && !session?.user && (
        <Card>
          <CardHeader>
            <CardTitle>Access</CardTitle>
            <CardDescription>
              Registration and sign-in
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
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
    </div>
  )
}
