import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { cookies } from 'next/headers'
import './globals.css'
import AppSidebar from '@/components/layout/AppSidebar'
import TopBar from '@/components/layout/TopBar'
import Footer from '@/components/layout/Footer'
import Providers from './providers'
import SessionMonitor from '@/components/auth/SessionMonitor'
import CookieNotice from '@/components/common/CookieNotice'
import BetaPhaseLoginNotice from '@/components/common/BetaPhaseLoginNotice'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'
import { SIDEBAR_COOKIE, parseSidebarChoice } from '@/lib/sidebarState'
import { getBetaBannerText, getBetaLoginMessage, isBetaPhaseEnabled } from '@/lib/beta'
import { ThemeProvider } from 'next-themes'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'CSC - Catalog of Second Chances',
  description: 'A components and materials database.',
}

// Beta/gh-interface flags come from the server's .env at request time. Without
// this, prerendering bakes in whatever the CI build machine saw (i.e. nothing).
export const dynamic = 'force-dynamic'

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const betaPhaseEnabled = isBetaPhaseEnabled()
  // the sidebar choice is read on the server, so the first paint has the
  // right width (decision 8.29)
  const sidebarChoice = parseSidebarChoice((await cookies()).get(SIDEBAR_COOKIE)?.value)

  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen`}>
        <ThemeProvider
          attribute="class"         // adds "light"/"dark" on <html>
          defaultTheme="system"     // server renders neutral; client sets "system"
          enableSystem={true}       // enable system theme detection
          disableTransitionOnChange // no flicker on toggle
          storageKey="csc-theme"   // use a new key so old `theme=dark` is ignored
          themes={['light','dark','system']} // explicit themes including system
        >
          <Providers>
            <SessionMonitor />
            {betaPhaseEnabled && <BetaPhaseLoginNotice message={getBetaLoginMessage()} />}
            <CookieNotice />
            <SidebarProvider initialChoice={sidebarChoice}>
              <AppSidebar
                betaBannerText={betaPhaseEnabled ? getBetaBannerText() : undefined}
              />
              <SidebarInset>
                <TopBar betaBannerText={betaPhaseEnabled ? getBetaBannerText() : undefined} />
                <main className="w-full max-w-full flex-1 overflow-x-hidden">{children}</main>
                <footer className="w-full">
                  <Footer />
                </footer>
              </SidebarInset>
            </SidebarProvider>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  )
}
