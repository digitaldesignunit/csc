import { redirect } from 'next/navigation'

/** Reserved became a part of My work (decision 8.118 Q4). */
export default function ReservedRedirect() {
  redirect('/my-work')
}
