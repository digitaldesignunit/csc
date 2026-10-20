import AccessTokensSection from '@/components/settings/AccessTokensSection'
import AccountSection from '@/components/settings/AccountSection'
import ChangePasswordSection from '@/components/settings/ChangePasswordSection'
import CookieSettingsSection from '@/components/settings/CookieSettingsSection'
import ProfileSection from '@/components/settings/ProfileSection'
import ThemeSettingsSection from '@/components/settings/ThemeSettingsSection'

/** One page of short sections (plan P11 stage 3, decision 8.118 S6; the profile 8.133 b). */
export default function SettingsPage() {
  return (
    <div className="mx-auto w-full max-w-2xl space-y-4 p-3 sm:p-6">
      <h1 className="text-xl font-bold sm:text-2xl">Settings</h1>
      <AccountSection />
      <ProfileSection />
      <ChangePasswordSection />
      <AccessTokensSection />
      <ThemeSettingsSection />
      <CookieSettingsSection />
    </div>
  )
}
