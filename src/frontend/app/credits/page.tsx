import { existsSync } from 'node:fs'
import { join } from 'node:path'
import Image from 'next/image'

import BackgroundMesh from '@/components/components/BackgroundMesh'
import BibtexCitation from '@/components/credits/BibtexCitation'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Award, Users, Code, ExternalLink, BookOpen } from 'lucide-react'

import { LINK } from '@/lib/legalPage'

const FERTIGTEIL_URL = 'https://www.dg.architektur.tu-darmstadt.de/forschung_ddu/digitale_prozessketten_ddu/computational_design/fertigteil_2__0/fertigteile_2__0.en.jsp'
const ZIRKUS_URL = 'https://www.dg.architektur.tu-darmstadt.de/forschung_ddu/digitale_prozessketten_ddu/computational_design/zirkus/zirkus.en.jsp'
const BMFTR_URL = 'https://www.bmftr.bund.de/'
const REMIN_URL = 'https://www.fona.de/en/measures/funding-measures/Resource-efficient-circular-economy-building-and-mineral-cycles.php'
const DBU_PROJECT_URL = 'https://www.dbu.de/projektdatenbank/40160-01/'

type FundingLogo = { file: string; alt: string; href: string }

/** One file each, in `public/logo/funding/`. A logo whose file is not there yet is left out. */
const DBU_LOGO: FundingLogo = {
  file: 'dbu-sponsored-by.png',
  alt: 'Deutsche Bundesstiftung Umwelt (DBU): sponsored by',
  href: DBU_PROJECT_URL,
}
const BMBF_LOGO: FundingLogo = {
  file: 'bmbf.svg',
  alt: 'Funded by the Federal Ministry of Education and Research (BMBF)',
  href: BMFTR_URL,
}

function logoAvailable(file: string): boolean {
  try {
    return existsSync(join(process.cwd(), 'public', 'logo', 'funding', file))
  } catch {
    return false
  }
}

function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noreferrer noopener" className={LINK}>
      {children}
    </a>
  )
}

/** A funding statement with its logo on a light tile (the logos are drawn for a light ground). */
function FundingItem({ title, logo, children }: { title: string; logo?: FundingLogo; children: React.ReactNode }) {
  const show = logo !== undefined && logoAvailable(logo.file)
  return (
    <li className="flex flex-col gap-4 border-l-2 border-primary/40 pl-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-1.5">
        <h3 className="text-base font-semibold">{title}</h3>
        <p className="text-sm leading-relaxed">{children}</p>
      </div>
      {show && logo && (
        <a href={logo.href} target="_blank" rel="noreferrer noopener"
          className="shrink-0 self-start rounded-md bg-white p-2 ring-1 ring-border">
          <Image src={`/logo/funding/${logo.file}`} alt={logo.alt} width={600} height={600} sizes="160px"
            unoptimized={logo.file.endsWith('.svg')}
            style={{ height: '7rem', width: 'auto', maxWidth: '10rem' }} className="object-contain" />
        </a>
      )}
    </li>
  )
}

const CSC_BIBTEX = `@software{eschenbach_catalog_2026,
	title = {Catalog of {Second} {Chances} ({CSC}) - {Digital} {Database} and {Corresponding} {Interfaces} for {ReUse} of {Architectural} {Components}},
	copyright = {MIT License, Copyright (C) 2024-2026 by the Authors},
	url = {https://zenodo.org/doi/10.5281/zenodo.20156666},
	doi = {10.5281/ZENODO.20156666},
	abstract = {The Catalog of Second Chances (CSC) provides a prototypical platform and the corresponding tools to leverage a database of uniquely identified, digitized architectural components for creating designs that reuse these components.},
	publisher = {Zenodo},
	author = {Eschenbach, Max Benjamin},
	month = may,
	year = {2026},
	note = {Language: en},
}`

export default function CreditsPage() {
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
            <Award className="h-6 w-6 text-primary" aria-hidden />
            <h1 className="text-xl font-bold sm:text-2xl">Credits</h1>
          </div>
          <p className="text-sm text-muted-foreground sm:text-base">
            Credits, Sources & References for the <em>Catalog of Second Chances</em>
          </p>
        </div>

        {/* Main Content */}
        <div className="relative z-10 space-y-6">
        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BookOpen className="h-5 w-5" />
              Research Context
            </CardTitle>
          </CardHeader>

          <CardContent className="space-y-4 text-sm leading-relaxed">
            <p>
              This piece of software and the underlying research is part of the
              PhD thesis <em>Collaborative Computational Reuse</em> of <a href='https://www.researchgate.net/profile/Max-Eschenbach' target='_blank' className={LINK}>Max Eschenbach</a> at
              the <a href='https://www.dg.architektur.tu-darmstadt.de/fachgebiet_ddu/index.de.jsp' target='_blank' className={LINK}>Digital Design Unit (DDU)</a>
              , supervised and chaired by Prof. Dr.-Ing. Oliver Tessmann, at the <a href='https://www.tu-darmstadt.de/' target='_blank' className={LINK}>Technical University of Darmstadt</a>.
            </p>
            <p>
              If you want to reference or cite this work, please use the following BibTeX entry:
            </p>
            <BibtexCitation bibtex={CSC_BIBTEX} />
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Award className="h-5 w-5" />
              Public Funding
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-5">
              <FundingItem
                title="Fertigteil 2.0 (Precast Concrete Components 2.0)"
                logo={BMBF_LOGO}
              >
                Part of this research was conducted within the project{' '}
                <em>
                  <ExtLink href={FERTIGTEIL_URL}>
                    Fertigteil 2.0 - Real-digital process chains for the production of built-in concrete components
                  </ExtLink>
                </em>
                . The project was funded by the{' '}
                <ExtLink href={BMFTR_URL}>
                  Federal Ministry of Education and Research Germany (BMBF)
                </ExtLink>{' '}
                through the funding measure{' '}
                <ExtLink href={REMIN_URL}>
                  Resource-efficient circular economy - Building and mineral cycles (ReMin)
                </ExtLink>
                .
              </FundingItem>
              <FundingItem title="ZirKuS" logo={DBU_LOGO}>
                Part of this research was conducted within the project{' '}
                <em>
                  <ExtLink href={ZIRKUS_URL}>
                    ZirKuS - Circular Construction and Structural Design of Reused Concrete Components
                  </ExtLink>
                </em>
                . The project is funded by the{' '}
                <ExtLink href={DBU_PROJECT_URL}>Deutsche Bundesstiftung Umwelt - DBU</ExtLink>{' '}
                (German Federal Environmental Foundation) within the funding line{' '}
                <ExtLink href="https://www.dbu.de/foerderung/projektfoerderung/foerderthemen/klima-und-ressourcenschonendes-bauen/">
                  Climate- and Resource-Efficient Construction
                </ExtLink>
                .
              </FundingItem>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-5 w-5" />
              Student Work
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>
                Idea and prototype code for <code className='bg-accent/40 px-1 py-0.5 rounded'>FindLargestFlatSide</code> by Alessandro Garruto. The code has been refactored and integrated by Max Eschenbach.
              </li>
              <li>
                Idea and prototype code for <code className='bg-accent/40 px-1 py-0.5 rounded'>MaxInscribedQuad</code> by Alessandro Garruto. The code has been refactored and integrated by Max Eschenbach.
              </li>
              <li>
                The <code className='bg-accent/40 px-1 py-0.5 rounded'>csc_labels</code> python code to create the QR-Code labels was developed by <a href='https://instagram.com/mirkodutschke' target='_blank' className={LINK}>Mirko Dutschke</a>. The code has
                been refactored as a python module and integrated by Max Eschenbach.
              </li>
              <li>
                The <code className='bg-accent/40 px-1 py-0.5 rounded'>csc_sheetscan</code> python module was developed based on the scanning setup
                for sheets that was developed by <a href='https://instagram.com/mirkodutschke' target='_blank' className={LINK}>Mirko Dutschke</a>. The functional code has been written by Max Eschenbach.
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Code className="h-5 w-5" />
              Licensing
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>Original code is licensed under the <a href='https://github.com/digitaldesignunit/csc?tab=MIT-1-ov-file' target='_blank' className={LINK}>MIT License</a>.</li>
              <li>
                The <code className='bg-accent/40 px-1 py-0.5 rounded'>csc_sheetscan</code> module makes heavy use of the <a href='https://opencv.org/' target='_blank' className={LINK}>OpenCV</a> library, more specifically its <a href='https://anaconda.org/conda-forge/opencv' target='_blank' className={LINK}>pre-built packages for python</a> via conda-forge.
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ExternalLink className="h-5 w-5" />
              References
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>
                The technical main inspiration for the <em>Catalog of Second Chances</em> interface is the <a href='https://github.com/ibois-epfl/catalogue-explorer' target='_blank' className={LINK}>Catalog Explorer</a> by <a href='https://github.com/AymericBr' target='_blank' className={LINK}>@AymbericBr</a>.
              </li>
              <li>
                Another huge inspiration and reference is the <a href='https://epfl-enac.github.io/MANSLAB-IBOIS-EESD-timberstone/' target='_blank' className={LINK}>Timberstone Project</a>, which is the origin of abovementioned Catalog Explorer.
              </li>
              <li>
                The simple shape descriptors (BoxScore, SphereScore, PlaneScore, LineScore) are computed based on the reference implementation of <a href='https://github.com/keithjlee/DigitalCircularityToolkit' target='_blank' className={LINK}>DigitalCircularityToolkit</a> by <a href='https://github.com/keithjlee' target='_blank' className={LINK}>Keith J. Lee</a>.
              </li>
              <li>
                Huge thanks to <a href='https://sandrosiefert.com/beyond-debris/' target='_blank' className={LINK}>Sandro Siefert</a> for his inspirational work and the contribution of his debris dataset. Looking forward to continue this research with you!
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Code className="h-5 w-5" />
              Open Source & Third Party Libraries
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>
                <strong>Frontend Framework:</strong> <a href='https://nextjs.org/' target='_blank' className={LINK}>Next.js</a> - React framework
              </li>
              <li>
                <strong>UI Components:</strong> <a href='https://ui.shadcn.com/' target='_blank' className={LINK}>shadcn/ui</a> - Re-usable React components
              </li>
              <li>
                <strong>3D Graphics:</strong> <a href='https://r3f.docs.pmnd.rs/' target='_blank' className={LINK}>React Three Fiber</a> & <a href='https://github.com/pmndrs/drei' target='_blank' className={LINK}>Drei</a> - React renderer for Three.js
              </li>
              <li>
                <strong>Styling:</strong> <a href='https://tailwindcss.com/' target='_blank' className={LINK}>Tailwind CSS</a> - CSS framework
              </li>
              <li>
                <strong>Authentication:</strong> <a href='https://next-auth.js.org/' target='_blank' className={LINK}>NextAuth.js</a> - Authentication for Next.js
              </li>
              <li>
                <strong>Database:</strong> <a href='https://www.mongodb.com/' target='_blank' className={LINK}>MongoDB</a> - NoSQL database
              </li>
              <li>
                <strong>Backend Framework:</strong> <a href='https://fastapi.tiangolo.com/' target='_blank' className={LINK}>FastAPI</a> - Python web framework for building APIs
              </li>
              <li>
                <strong>Computer Vision:</strong> <a href='https://opencv.org/' target='_blank' className={LINK}>OpenCV</a> - Computer vision and machine learning library
              </li>
              <li>
                <strong>Mesh Processing:</strong> <a href='https://trimesh.org/' target='_blank' className={LINK}>Trimesh</a> - Python library for loading and using triangular meshes
              </li>
              <li>
                <strong>Scientific Computing:</strong> <a href='https://numpy.org/' target='_blank' className={LINK}>NumPy</a>, <a href='https://scipy.org/' target='_blank' className={LINK}>SciPy</a>, <a href='https://scikit-learn.org/' target='_blank' className={LINK}>scikit-learn</a> - Scientific computing libraries
              </li>
              <li>
                <strong>QR Code Processing:</strong> <a href='https://github.com/Eric-Canas/qreader' target='_blank' className={LINK}>qreader</a> - QR code reader library
              </li>
              <li>
                <strong>Data Validation:</strong> <a href='https://pydantic.dev/' target='_blank' className={LINK}>Pydantic</a> - Data validation using Python type annotations
              </li>
              <li>
                <strong>Icons:</strong> <a href='https://lucide.dev/' target='_blank' className={LINK}>Lucide React</a> - Icon toolkit for React
              </li>
            </ul>
          </CardContent>
        </Card>
        </div>
      </div>
    </div>
  )
}