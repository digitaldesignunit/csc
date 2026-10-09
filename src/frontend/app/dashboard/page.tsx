import { redirect } from 'next/navigation'

/** The Dashboard became My work (decision 8.118 Q4). */
export default function DashboardRedirect() {
  redirect('/my-work')
}
