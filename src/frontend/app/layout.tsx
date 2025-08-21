import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Sidebar from '@/components/layout/Sidebar'
import Header from '@/components/layout/Header'
import Footer from '@/components/layout/Footer'
import Providers from './providers'
import { ThemeProvider } from 'next-themes'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'CSC - Catalogue of Second Chances',
  description: 'A components and materials database.',
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.className} min-h-screen flex flex-col`}>
        <ThemeProvider
          attribute="class"         // adds "light"/"dark" on <html>
          defaultTheme="light"      // server renders neutral; client sets "light"
          enableSystem={false}      // ignore OS to avoid surprises
          disableTransitionOnChange // no flicker on toggle
          storageKey="csc-theme"   // use a new key so old `theme=dark` is ignored
          themes={['light','dark']} // explicit
        >
          <Providers>
            <div className="flex-grow grid md:grid-cols-[250px_1fr]">
              {/* Desktop Sidebar - hidden on mobile */}
              <div className="h-full hidden md:block md:shrink-10 min-w-[250px] border-r">
                <Sidebar />
              </div>

              {/* Main Content Area */}
              <main className="ml-0 min-h-screen">
                <Header />
                <div className="grid w-full">{children}</div>
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
