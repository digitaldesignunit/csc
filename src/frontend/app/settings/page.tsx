import AccountSection from '@/components/settings/AccountSection'
import ChangePasswordSection from '@/components/settings/ChangePasswordSection'
import CookieSettingsSection from '@/components/settings/CookieSettingsSection'
import ThemeSettingsSection from '@/components/settings/ThemeSettingsSection'

/** One page, four short sections (plan P11 stage 3, decision 8.118 S6). */
export default function SettingsPage() {
  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 p-3 sm:p-6">
      <h1 className="text-xl font-bold sm:text-2xl">Settings</h1>
      <AccountSection />
      <ChangePasswordSection />
      <ThemeSettingsSection />
      <CookieSettingsSection />
    </div>
  )
}
