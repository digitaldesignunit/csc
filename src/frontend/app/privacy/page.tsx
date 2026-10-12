import Link from 'next/link'
import { Shield } from 'lucide-react'

import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export const metadata = { title: 'Privacy' }

/** The day this text was last changed: the one place to edit with the text. */
const LAST_UPDATED = '12 October 2026'

/** The controller's address for requests: the one on the Imprint. */
const CONTACT_EMAIL = 'max.eschenbach@tu-darmstadt.de'

const LINK = 'font-medium text-primary underline underline-offset-2 hover:opacity-80'

/** What is processed, why, on which legal basis, how long. */
const ROWS: { what: string; why: string; basis: string; kept: string }[] = [
  {
    what: 'Account: username, e-mail address, password (stored as a salted hash only), role and dataset memberships; your full name if you give it.',
    why: 'To sign you in and to show who added or changed a record.',
    basis: 'Art. 6(1)(b) GDPR',
    kept: 'Until you ask for the account to be deleted.',
  },
  {
    what: 'Profile (optional): organisation, ROR, ORCID and your usual role. It is copied into the records you make.',
    why: 'To fill in "performed by" for you.',
    basis: 'Art. 6(1)(a) GDPR, your consent',
    kept: 'Until you change or clear it; copies stay in your records.',
  },
  {
    what: 'Contributions: components, evidence records, photos and files, with your username. Names and ORCID in "performed by" are shown to signed-in users only.',
    why: 'The catalogue itself: a documented record of re-used building components.',
    basis: 'Art. 6(1)(f) GDPR, the research interest in a documented catalogue',
    kept: 'Published records are withdrawn, not deleted; on request the personal data in them is redacted.',
  },
  {
    what: 'E-mails: address verification, password reset, invitations and notices about records.',
    why: 'To run your account and the review of contributions. No newsletters.',
    basis: 'Art. 6(1)(b) GDPR',
    kept: 'The site keeps no copy of sent mails.',
  },
  {
    what: "Server logs: the hosting provider's web server logs your IP address, the time and the requested page. The site's own request log keeps the time, the requested page, the status and the name of your browser or program (no IP address).",
    why: 'Operation and security.',
    basis: 'Art. 6(1)(f) GDPR',
    kept: "The hosting provider keeps its logs for a short period; the site's own log is deleted after 14 days.",
  },
  {
    what: 'Cookies and your device: the sign-in cookie, and on your device the theme, your Browse columns, the pieces you opened last and this notice being closed.',
    why: 'Sign-in and your settings. No tracking, no statistics, nothing loaded from other sites.',
    basis: 'Section 25(2) TDDDG, needed for the service',
    kept: 'The cookie ends with your session; the rest stays on your device until you clear it.',
  },
]

export default function PrivacyPage() {
  return (
    <div className="relative min-h-full">
      <BackgroundMesh
        className="absolute inset-0 -z-10"
        opacity={0.08}
        rotationSpeed={0.15}
        intensity={0.2}
        scale={0.7}
      />

      <div className="container mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
        <div className="mb-4 sm:mb-6">
          <div className="mb-2 flex items-center gap-2 sm:gap-3">
            <Shield className="h-6 w-6 text-primary" aria-hidden />
            <h1 className="text-xl font-bold sm:text-2xl">Privacy</h1>
          </div>
          <p className="text-sm text-muted-foreground sm:text-base">
            What the <em>Catalog of Second Chances</em> does with personal data
          </p>
          <p className="mt-1 text-xs text-muted-foreground">Last updated: {LAST_UPDATED}</p>
        </div>

        <div className="relative z-10">
          <Card className="bg-card/75">
            <CardHeader>
              <CardTitle className="text-base">Controller</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6 text-sm leading-relaxed">
              <p>
                Max Eschenbach, Lahnstr. 67, 60326 Frankfurt am Main, Germany. E-mail:{' '}
                <a href={`mailto:${CONTACT_EMAIL}`} className={LINK}>{CONTACT_EMAIL}</a> (as in the{' '}
                <Link href="/imprint" className={LINK}>Imprint</Link>).
              </p>

              <ul className="space-y-4">
                {ROWS.map((row) => (
                  <li key={row.what} className="space-y-1 border-l-2 border-primary/40 pl-4">
                    <p className="font-medium">{row.what}</p>
                    <p className="text-muted-foreground">
                      {row.why} {row.basis}. {row.kept}
                    </p>
                  </li>
                ))}
              </ul>

              <p>
                Data is processed on our behalf by the hosting provider (Uberspace), the database provider (MongoDB
                Atlas, data stored in the EU, in Belgium) and the provider that delivers the e-mails. MongoDB, Inc. is
                based in the United States; any access from there, for example by its support, rests on the
                provider&apos;s data processing agreement with EU standard contractual clauses or the EU-US Data
                Privacy Framework. Data is not passed on otherwise, and there is no automated decision-making.
              </p>

              <p>
                <strong>Your rights:</strong> access (Art. 15), rectification (Art. 16, your profile is in Settings),
                erasure (Art. 17), restriction (Art. 18), portability (Art. 20), objection (Art. 21) and withdrawal of
                a consent (Art. 7(3)). Write to <a href={`mailto:${CONTACT_EMAIL}`} className={LINK}>{CONTACT_EMAIL}</a> or to the postal address
                above to use them. You may complain to the Hessian
                Commissioner for Data Protection and Freedom of Information in Wiesbaden.
              </p>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
