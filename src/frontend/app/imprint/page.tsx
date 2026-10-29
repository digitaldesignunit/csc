import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, Shield, Copyright } from 'lucide-react'

import { LINK } from '@/lib/legalPage'

export default function ImprintPage() {
  return (
    <div className="relative min-h-full">
      {/* Background Mesh */}
      <BackgroundMesh
        className="absolute inset-0 -z-10"
        opacity={0.08}
        rotationSpeed={0.15}
        intensity={0.2}
        scale={0.7}
      />

      <div className="container mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
        {/* Header */}
        <div className="mb-4 sm:mb-6">
          <div className="mb-2 flex items-center gap-2 sm:gap-3">
            <FileText className="h-6 w-6 text-primary" aria-hidden />
            <h1 className="text-xl font-bold sm:text-2xl">Imprint</h1>
          </div>
          <p className="text-sm text-muted-foreground sm:text-base">
            Legal information and contact details
          </p>
        </div>

        {/* Main Content */}
        <div className="relative z-10 space-y-6">
        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-5 w-5" />
              Contact Information
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
            <div className="space-y-2">
              <p><strong>&copy;</strong> Max Eschenbach 2024-2026</p>
              <div className="space-y-1">
                <p>Max Eschenbach</p>
                <p>Lahnstr. 67</p>
                <p>60326 Frankfurt am Main</p>
                <p>Deutschland</p>
              </div>
              <p><strong>E-Mail:</strong> <a href="mailto:max.eschenbach@tu-darmstadt.de" className={LINK}>max.eschenbach@tu-darmstadt.de</a></p>
              <p className="text-sm text-muted-foreground">
                Der Katalog ist Teil eines Promotionsprojekts am Fachgebiet Digitales Gestalten (Digital Design Unit,
                DDU), TU Darmstadt, El-Lissitzky-Stra&szlig;e 1, 64287 Darmstadt, Deutschland. Anbieter dieses Angebots und
                Verantwortlicher im Sinne der DSGVO ist Max Eschenbach pers&ouml;nlich. Die TU Darmstadt betreibt den
                Katalog nicht und ist f&uuml;r ihn nicht verantwortlich.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Shield className="h-5 w-5" />
              Disclaimer
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
            <div>
              <h3 className="mb-2 text-base font-semibold">Haftung für Inhalte</h3>
              <p className="mb-4">
                Alle Inhalte unseres Internetauftritts wurden mit größter Sorgfalt und nach bestem Gewissen erstellt. Für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte können wir jedoch keine Gewähr übernehmen. Als Diensteanbieter sind wir gemäß § 7 Abs. 1 DDG für eigene Inhalte auf diesen Seiten nach den allgemeinen Gesetzen verantwortlich. Nach §§ 8 bis 10 DDG sind wir als Diensteanbieter jedoch nicht verpflichtet, übermittelte oder gespeicherte fremde Informationen zu überwachen oder nach Umständen zu forschen, die auf eine rechtswidrige Tätigkeit hinweisen. Verpflichtungen zur Entfernung oder Sperrung der Nutzung von Informationen nach den allgemeinen Gesetzen bleiben hiervon unberührt.
              </p>
              <p className="mb-4">
                Eine diesbezügliche Haftung ist jedoch erst ab dem Zeitpunkt der Kenntniserlangung einer konkreten Rechtsverletzung möglich. Bei Bekanntwerden von den o.g. Rechtsverletzungen werden wir diese Inhalte unverzüglich entfernen.
              </p>
            </div>
            
            <div>
              <h3 className="mb-2 text-base font-semibold">Haftungsbeschränkung für externe Links</h3>
              <p className="mb-4">
                Unsere Webseite enthält Links auf externe Webseiten Dritter. Auf die Inhalte dieser direkt oder indirekt verlinkten Webseiten haben wir keinen Einfluss. Daher können wir für die &ldquo;externen Links&rdquo; auch keine Gewähr auf Richtigkeit der Inhalte übernehmen. Für die Inhalte der externen Links sind die jeweilige Anbieter oder Betreiber (Urheber) der Seiten verantwortlich.
              </p>
              <p className="mb-4">
                Die externen Links wurden zum Zeitpunkt der Linksetzung auf eventuelle Rechtsverstöße überprüft und waren im Zeitpunkt der Linksetzung frei von rechtswidrigen Inhalten. Eine ständige inhaltliche Überprüfung der externen Links ist ohne konkrete Anhaltspunkte einer Rechtsverletzung nicht möglich. Bei direkten oder indirekten Verlinkungen auf die Webseiten Dritter, die außerhalb unseres Verantwortungsbereichs liegen, würde eine Haftungsverpflichtung ausschließlich in dem Fall nur bestehen, wenn wir von den Inhalten Kenntnis erlangen und es uns technisch möglich und zumutbar wäre, die Nutzung im Falle rechtswidriger Inhalte zu verhindern.
              </p>
              <p className="mb-4">
                Diese Haftungsausschlusserklärung gilt auch innerhalb des eigenen Internetauftrittes &ldquo;<em>Catalog of Second Chances</em>&rdquo; gesetzten Links und Verweise von Fragestellern, Blogeinträgern, Gästen des Diskussionsforums. Für illegale, fehlerhafte oder unvollständige Inhalte und insbesondere für Schäden, die aus der Nutzung oder Nichtnutzung solcherart dargestellten Informationen entstehen, haftet allein der Diensteanbieter der Seite, auf welche verwiesen wurde, nicht derjenige, der über Links auf die jeweilige Veröffentlichung lediglich verweist.
              </p>
              <p>
                Werden uns Rechtsverletzungen bekannt, werden die externen Links durch uns unverzüglich entfernt.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Copyright className="h-5 w-5" />
              Copyright
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
            <p>
              Die auf unserer Webseite veröffentlichen Inhalte und Werke unterliegen dem deutschen Urheberrecht (<a href="http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf" target="_blank" rel="noreferrer noopener" className={LINK}>http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf</a>). Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art der Verwertung des geistigen Eigentums in ideeller und materieller Sicht des Urhebers außerhalb der Grenzen des Urheberrechtes bedürfen der vorherigen schriftlichen Zustimmung des jeweiligen Urhebers i.S.d. Urhebergesetzes (<a href="http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf" target="_blank" rel="noreferrer noopener" className={LINK}>http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf</a>). Downloads und Kopien dieser Seite sind nur für den privaten und nicht kommerziellen Gebrauch erlaubt. Sind die Inhalte auf unserer Webseite nicht von uns erstellt wurden, sind die Urheberrechte Dritter zu beachten. Die Inhalte Dritter werden als solche kenntlich gemacht. Sollten Sie trotzdem auf eine Urheberrechtsverletzung aufmerksam werden, bitten wir um einen entsprechenden Hinweis. Bei Bekanntwerden von Rechtsverletzungen werden wir derartige Inhalte unverzüglich entfernen.
            </p>
            <p>
              Dieses <a href="https://jurarat.de/muster-impressum" className={LINK}>Impressum</a> wurde freundlicherweise von <a href="https://jurarat.de/" className={LINK}>jurarat.de</a> zur Verfügung gestellt.
            </p>
          </CardContent>
        </Card>
        </div>
      </div>
    </div>
  )
}