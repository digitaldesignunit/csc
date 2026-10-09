import { redirect } from 'next/navigation'

/** The verification queue is a tab of the Moderation page (decision 8.118 S2). */
export default function ReviewRedirect() {
  redirect('/admin/validation?tab=verification')
}
