import { redirect } from 'next/navigation'

/** The admin index is the Moderation page (decision 8.118 S2). */
export default function AdminIndex() {
  redirect('/admin/validation')
}
