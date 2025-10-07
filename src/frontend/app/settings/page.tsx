import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import CookieSettingsSection from '@/components/settings/CookieSettingsSection'

export default function SettingsPage() {
  return (
    <div className='grid gap-[32px] m-4'>
      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>Manage your account and privacy preferences</CardDescription>
        </CardHeader>
      </Card>
      
      <CookieSettingsSection />
    </div>
  )
}