import Link from 'next/link'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

export const metadata = {
  title: '404 – Page not found',
}

export default function NotFound() {
  return (
    <div className="min-h-[60vh] grid place-items-center px-4 py-16 bg-background text-foreground">
      <Card className="w-full max-w-xl">
        <CardHeader>
          <CardTitle>Page not found</CardTitle>
          <CardDescription>
            The requested page could not be located.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Use one of the options below to continue.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/">
              <Button className="bg-primary text-primary-foreground hover:opacity-90">
                Go to Home
              </Button>
            </Link>
            <Link href="/components">
              <Button variant="outline">Browse Components</Button>
            </Link>
          </div>
          <div className="h-px w-full bg-border" />
          <p className="text-xs text-muted-foreground">
            If you believe this URL should exist, check the address or report the issue.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
