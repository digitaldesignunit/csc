import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Sidebar from '@/components/Sidebar'
import Header from '@/components/Header'
import Footer from '@/components/Footer'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'CSC - Catalogue of Second Chances',
  description: 'A components and materials database.',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang='en'>
      <body className={`${inter.className} min-h-screen flex flex-col`}>
        
        <div className='flex-grow grid md:grid-cols-[250px_1fr]'>

          <div className='h-full hidden md:block md:shrink-10 min-w-[250px] border-r'>
            <Sidebar/>
          </div>

          <main className='ml-0'>

            <Header/>

            <div className='grid w-full'>
              {children}
            </div>
            
          </main>
        
        </div>

        <footer className='w-full'>
          <Footer/>
        </footer>

      </body>
    </html>
  )
}
