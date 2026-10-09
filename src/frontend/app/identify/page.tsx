import { redirect } from 'next/navigation'

/** Scan & Identify moved into the Scan page (decision 8.118 Q7). */
export default function IdentifyRedirect() {
  redirect('/scan')
}
