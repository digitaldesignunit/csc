import { redirect } from 'next/navigation'

/** Transmit ID moved into the Scan page (decision 8.118 Q7). */
export default function TransmitRedirect() {
  redirect('/scan?mode=transmit')
}
