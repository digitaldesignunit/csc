import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function ImprintPage() {
  return (
    <div className='grid gap-[32px] m-4'>
      <Card>
        <CardHeader>
          <CardTitle>Imprint</CardTitle>
          <CardDescription>
          </CardDescription>
        </CardHeader>
        <CardContent>
        <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Angaben gem. § 5 TMG</h2>
            <p className='mb-4'>
              <p><strong>©</strong> Max Benjamin Eschenbach 2024</p>
              <p><strong>E-Mail:</strong> <a href="mailto:eschenbach@dg.tu-darmstadt.de">eschenbach@dg.tu-darmstadt.de</a></p>
              <br></br>
              <p>Fachgebiet Digitales Gestalten (Digital Design Unit, DDU)</p>
              <p>TU Darmstadt</p>
              <p>El-Lissitzky-Straße 1</p>
              <p>64287 Darmstadt</p>
              <p>Deutschland</p>
            </p>
          </section>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Haftungsausschluss - Disclaimer:</h2>
            <h3 className='text-l font-bold mb-1'>Haftung für Inhalte</h3>
            <p>Alle Inhalte unseres Internetauftritts wurden mit größter Sorgfalt und nach bestem Gewissen erstellt. Für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte können wir jedoch keine Gewähr übernehmen. Als Diensteanbieter sind wir gemäß § 7 Abs.1 TMG für eigene Inhalte auf diesen Seiten nach den allgemeinen Gesetzen verantwortlich. Nach §§ 8 bis 10 TMG sind wir als Diensteanbieter jedoch nicht verpflichtet, übermittelte oder gespeicherte fremde Informationen zu überwachen oder nach Umständen zu forschen, die auf eine rechtswidrige Tätigkeit hinweisen. Verpflichtungen zur Entfernung oder Sperrung der Nutzung von Informationen nach den allgemeinen Gesetzen bleiben hiervon unberührt.</p>
            <p>Eine diesbezügliche Haftung ist jedoch erst ab dem Zeitpunkt der Kenntniserlangung einer konkreten Rechtsverletzung möglich. Bei Bekanntwerden von den o.g. Rechtsverletzungen werden wir diese Inhalte unverzüglich entfernen.</p>
            <br></br>
            <h3 className='text-l font-bold mb-1'>Haftungsbeschränkung für externe Links</h3>
            <p>Unsere Webseite enthält Links auf externe Webseiten Dritter. Auf die Inhalte dieser direkt oder indirekt verlinkten Webseiten haben wir keinen Einfluss. Daher können wir für die „externen Links“ auch keine Gewähr auf Richtigkeit der Inhalte übernehmen. Für die Inhalte der externen Links sind die jeweilige Anbieter oder Betreiber (Urheber) der Seiten verantwortlich.</p>
            <p>Die externen Links wurden zum Zeitpunkt der Linksetzung auf eventuelle Rechtsverstöße überprüft und waren im Zeitpunkt der Linksetzung frei von rechtswidrigen Inhalten. Eine ständige inhaltliche Überprüfung der externen Links ist ohne konkrete Anhaltspunkte einer Rechtsverletzung nicht möglich. Bei direkten oder indirekten Verlinkungen auf die Webseiten Dritter, die außerhalb unseres Verantwortungsbereichs liegen, würde eine Haftungsverpflichtung ausschließlich in dem Fall nur bestehen, wenn wir von den Inhalten Kenntnis erlangen und es uns technisch möglich und zumutbar wäre, die Nutzung im Falle rechtswidriger Inhalte zu verhindern.</p>
            <p>Diese Haftungsausschlusserklärung gilt auch innerhalb des eigenen Internetauftrittes „<em>Catalogue of Second Chances</em>“ gesetzten Links und Verweise von Fragestellern, Blogeinträgern, Gästen des Diskussionsforums. Für illegale, fehlerhafte oder unvollständige Inhalte und insbesondere für Schäden, die aus der Nutzung oder Nichtnutzung solcherart dargestellten Informationen entstehen, haftet allein der Diensteanbieter der Seite, auf welche verwiesen wurde, nicht derjenige, der über Links auf die jeweilige Veröffentlichung lediglich verweist.</p>
            <p>Werden uns Rechtsverletzungen bekannt, werden die externen Links durch uns unverzüglich entfernt.</p>
          </section>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Urheberrecht</h2>
            <p>Die auf unserer Webseite veröffentlichen Inhalte und Werke unterliegen dem deutschen Urheberrecht (<a href="http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf" target="_blank" rel="noreferrer noopener">http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf</a>) . Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art der Verwertung des geistigen Eigentums in ideeller und materieller Sicht des Urhebers außerhalb der Grenzen des Urheberrechtes bedürfen der vorherigen schriftlichen Zustimmung des jeweiligen Urhebers i.S.d. Urhebergesetzes (<a href="http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf" target="_blank" rel="noreferrer noopener">http://www.gesetze-im-internet.de/bundesrecht/urhg/gesamt.pdf</a>&nbsp;). Downloads und Kopien dieser Seite sind nur für den privaten und nicht kommerziellen Gebrauch erlaubt. Sind die Inhalte auf unserer Webseite nicht von uns erstellt wurden, sind die Urheberrechte Dritter zu beachten. Die Inhalte Dritter werden als solche kenntlich gemacht. Sollten Sie trotzdem auf eine Urheberrechtsverletzung aufmerksam werden, bitten wir um einen entsprechenden Hinweis. Bei Bekanntwerden von Rechtsverletzungen werden wir derartige Inhalte unverzüglich entfernen.</p>
          
            <p>Dieses&nbsp;<a href="https://jurarat.de/muster-impressum">Impressum</a>&nbsp;wurde freundlicherweise von&nbsp;<a href="https://jurarat.de/">jurarat.de</a>&nbsp;zur Verfügung gestellt.</p>
          </section>
        </CardContent>
      </Card>
    </div>
  )
}