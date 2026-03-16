import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { FileText, Shield, Copyright } from 'lucide-react'

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

      <div className="container mx-auto p-6 space-y-6 max-w-6xl">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <FileText className="h-8 w-8 text-primary" />
            <h1 className="text-2xl sm:text-3xl font-bold">Imprint</h1>
          </div>
          <p className="text-muted-foreground text-sm sm:text-base">
            Legal information and contact details
          </p>
        </div>

        {/* Main Content */}
        <div className="relative z-10 space-y-6">
        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Contact Information
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <div className="space-y-2">
              <p><strong>©</strong> Max Benjamin Eschenbach 2024</p>
              <p><strong>E-Mail:</strong> <a href="mailto:eschenbach@dg.tu-darmstadt.de" className="text-blue-500 underline">eschenbach@dg.tu-darmstadt.de</a></p>
              <div className="mt-4 space-y-1">
                <p>Fachgebiet Digitales Gestalten (Digital Design Unit, DDU)</p>
                <p>TU Darmstadt</p>
                <p>El-Lissitzky-Straße 1</p>
                <p>64287 Darmstadt</p>
                <p>Deutschland</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" />
              Disclaimer
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <div>
              <h3 className="text-lg font-semibold mb-2">Haftung für Inhalte</h3>
              <p className="mb-4">
                Alle Inhalte unseres Internetauftritts wurden mit größter Sorgfalt und nach bestem Gewissen erstellt. Für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte können wir jedoch keine Gewähr übernehmen. Als Diensteanbieter sind wir gemäß § 7 Abs.1 TMG für eigene Inhalte auf diesen Seiten nach den allgemeinen Gesetzen verantwortlich. Nach §§ 8 bis 10 TMG sind wir als Diensteanbieter jedoch nicht verpflichtet, übermittelte oder gespeicherte fremde Informationen zu überwachen oder nach Umständen zu forschen, die auf eine rechtswidrige Tätigkeit hinweisen. Verpflichtungen zur Entfernung oder Sperrung der Nutzung von Informationen nach den allgemeinen Gesetzen bleiben hiervon unberührt.
              </p>
              <p className="mb-4">
                Eine diesbezügliche Haftung ist jedoch erst ab dem Zeitpunkt der Kenntniserlangung einer konkreten Rechtsverletzung möglich. Bei Bekanntwerden von den o.g. Rechtsverletzungen werden wir diese Inhalte unverzüglich entfernen.
              </p>
            </div>
            
            <div>
              <h3 className="text-lg font-semibold mb-2">Haftungsbeschränkung für externe Links</h3>
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
            <CardTitle className="flex items-center gap-2">
              <Copyright className="h-5 w-5" />
              Copyright
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <p>
              Die auf unserer Webseite veröffentlichen Inhalte und Werke unterliegen dem deutschen Urheberrecht (<a href="http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf" target="_blank" rel="noreferrer noopener" className="text-blue-500 underline">http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf</a>). Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art der Verwertung des geistigen Eigentums in ideeller und materieller Sicht des Urhebers außerhalb der Grenzen des Urheberrechtes bedürfen der vorherigen schriftlichen Zustimmung des jeweiligen Urhebers i.S.d. Urhebergesetzes (<a href="http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf" target="_blank" rel="noreferrer noopener" className="text-blue-500 underline">http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf</a>). Downloads und Kopien dieser Seite sind nur für den privaten und nicht kommerziellen Gebrauch erlaubt. Sind die Inhalte auf unserer Webseite nicht von uns erstellt wurden, sind die Urheberrechte Dritter zu beachten. Die Inhalte Dritter werden als solche kenntlich gemacht. Sollten Sie trotzdem auf eine Urheberrechtsverletzung aufmerksam werden, bitten wir um einen entsprechenden Hinweis. Bei Bekanntwerden von Rechtsverletzungen werden wir derartige Inhalte unverzüglich entfernen.
            </p>
            <p>
              Dieses <a href="https://jurarat.de/muster-impressum" className="text-blue-500 underline">Impressum</a> wurde freundlicherweise von <a href="https://jurarat.de/" className="text-blue-500 underline">jurarat.de</a> zur Verfügung gestellt.
            </p>
          </CardContent>
        </Card>
        </div>
      </div>
    </div>
  )
}