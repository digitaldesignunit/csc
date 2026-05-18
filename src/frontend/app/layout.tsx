import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Sidebar from '@/components/layout/Sidebar'
import Header from '@/components/layout/Header'
import Footer from '@/components/layout/Footer'
import Providers from './providers'
import SessionMonitor from '@/components/auth/SessionMonitor'
import CookieNotice from '@/components/common/CookieNotice'
import BetaPhaseBanner from '@/components/common/BetaPhaseBanner'
import BetaPhaseLoginNotice from '@/components/common/BetaPhaseLoginNotice'
import { getBetaLoginMessage, isBetaPhaseEnabled } from '@/lib/beta'
import { ThemeProvider } from 'next-themes'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'CSC - Catalog of Second Chances',
  description: 'A components and materials database.',
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const betaPhaseEnabled = isBetaPhaseEnabled()

  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen flex flex-col`}>
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
            <div className="flex-grow flex flex-col md:flex-row">
              {/* Desktop Sidebar - hidden on mobile */}
              <div className="hidden md:block md:w-[250px] md:flex-shrink-0 md:border-r">
                <Sidebar />
              </div>

              {/* Main Content Area */}
              <main className="flex-1 min-w-0 w-full md:w-auto">
                {betaPhaseEnabled && <BetaPhaseBanner />}
                <Header />
                <div className="w-full max-w-full overflow-x-hidden">{children}</div>
              </main>
            </div>

            <footer className="w-full">
              <Footer />
            </footer>
          </Providers>
        </ThemeProvider>
      </body>
    </html>
  )
}
