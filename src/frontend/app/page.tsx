'use client'

import Link from 'next/link'
import { useSession } from 'next-auth/react'
import { Globe, Workflow } from 'lucide-react'

import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * The home page (plan P11 stage 3, decision 8.118 C-1): the one page a
 * visitor can read, so the call to action comes first: browse. Then how the
 * catalog is used, then two sentences about it.
 */
export default function Home() {
  const { data: session, status } = useSession()
  const known = status !== 'loading'
  const signedIn = known && Boolean(session?.user) && !(session as { error?: string } | null)?.error

  return (
    <div className="relative min-h-[80vh] md:min-h-[90vh]">
      <BackgroundMesh
        className="absolute inset-0 -z-10"
        opacity={0.08}
        rotationSpeed={0.15}
        intensity={0.2}
        scale={1.0}
      />

      <div className="relative z-10 mx-auto w-full max-w-3xl space-y-5 p-4 sm:p-6">
        <section className="space-y-4 pt-4 sm:pt-10">
          <div className="space-y-2">
            <h1 className="text-2xl font-bold sm:text-3xl">Catalog of Second Chances</h1>
            <p className="text-base text-muted-foreground sm:text-lg">
              Find, record and reuse building components that have a second life ahead of them.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            {signedIn ? (
              <>
                <Button asChild size="lg"><Link href="/components">Browse</Link></Button>
                <Button asChild size="lg" variant="outline"><Link href="/scan">Scan a tag</Link></Button>
              </>
            ) : (
              <>
                <Button asChild size="lg"><Link href="/components">Browse the catalog</Link></Button>
                {known && (
                  <Button asChild size="lg" variant="outline"><Link href="/auth/signin">Sign in / Register</Link></Button>
                )}
              </>
            )}
          </div>
        </section>

        <Card className="bg-card/75">
          <CardHeader className="pb-2"><CardTitle className="text-base">How it is used</CardTitle></CardHeader>
          <CardContent className="grid gap-4 text-sm leading-relaxed sm:grid-cols-2">
            <div className="space-y-1">
              <p className="flex items-center gap-2 font-medium"><Globe className="h-4 w-4 text-primary" aria-hidden />On the web</p>
              <p>Browse and filter components, open a piece with its geometry and records, and on site record
                pieces and evidence from a phone.</p>
            </div>
            <div className="space-y-1">
              <p className="flex items-center gap-2 font-medium"><Workflow className="h-4 w-4 text-primary" aria-hidden />In Grasshopper</p>
              <p>Components for Rhino read and write the same catalog for design and documentation.
                See <Link href="/gh-interface" className="text-primary underline underline-offset-4">Grasshopper</Link>.</p>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader className="pb-2"><CardTitle className="text-base">About</CardTitle></CardHeader>
          <CardContent className="text-sm leading-relaxed">
            <p>
              The <i>Catalog of Second Chances</i> is a research and teaching repository of digitised building
              components that promotes reuse and circularity in architecture. It is developed as a case study
              of a doctoral thesis; <Link href="/credits" className="text-primary underline underline-offset-4">Credits</Link> has
              the details.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
