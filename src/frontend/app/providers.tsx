'use client';

import { SessionProvider } from 'next-auth/react';
import { Toaster } from '@/components/ui/sonner';
import { MeProvider } from '@/lib/me';
import { ReadOnlyProvider } from '@/components/common/ReadOnlyProvider';

export default function Providers({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider 
      refetchInterval={5 * 60} // Check session every 5 minutes
      refetchOnWindowFocus={true} // Check when window regains focus
      refetchWhenOffline={false} // Don't check when offline
    >
      <ReadOnlyProvider>
        <MeProvider>{children}</MeProvider>
      </ReadOnlyProvider>
      <Toaster richColors closeButton />
    </SessionProvider>
  );
}
