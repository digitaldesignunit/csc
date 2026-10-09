import Link from 'next/link'
import { PackagePlus, QrCode, Scissors } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/**
 * "This tag is not in the catalog yet" (spec 7.5, decision 8.87): shown only
 * to a signed-in caller with the contributor role in some dataset, for an id
 * no component has. The two actions open the snapshot form with the tag.
 */
export default function UnknownTag({ id }: { id: string }) {
  const query = (extra: string) => `/add-component?id=${encodeURIComponent(id)}&mode=${extra}`
  return (
    <div className="container mx-auto max-w-2xl space-y-4 p-4 sm:p-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <QrCode className="h-5 w-5 text-primary" />
            This tag is not in the catalog yet
          </CardTitle>
          <CardDescription>
            No component has this id. Record the piece it is stuck on, or a piece cut from others.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="break-all rounded-md bg-muted px-3 py-2 font-mono text-xs">{id}</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Button asChild className="h-auto justify-start gap-3 whitespace-normal p-4 text-left">
              <Link href={query('new')}>
                <PackagePlus className="h-5 w-5 shrink-0" />
                <span>
                  <span className="block font-medium">New component</span>
                  <span className="block text-xs font-normal opacity-90">Details, size and photos of this piece.</span>
                </span>
              </Link>
            </Button>
            <Button asChild variant="outline" className="h-auto justify-start gap-3 whitespace-normal p-4 text-left">
              <Link href={query('cut')}>
                <Scissors className="h-5 w-5 shrink-0" />
                <span>
                  <span className="block font-medium">Cut from pieces</span>
                  <span className="block text-xs font-normal text-muted-foreground">
                    Scan the parent tags next; this tag is the new piece.
                  </span>
                </span>
              </Link>
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
