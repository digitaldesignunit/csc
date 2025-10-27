import BackgroundMesh from '@/components/components/BackgroundMesh'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Award, Users, Code, ExternalLink, BookOpen } from 'lucide-react'

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

      <div className="container mx-auto p-6 space-y-6 max-w-6xl">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
          <div className="flex items-center gap-2 sm:gap-3 mb-2">
            <Award className="h-8 w-8 text-primary" />
            <h1 className="text-2xl sm:text-3xl font-bold">Credits</h1>
          </div>
          <p className="text-muted-foreground text-sm sm:text-base">
            Credits, Sources & References for the <em>Catalogue of Second Chances</em>
          </p>
        </div>

        {/* Main Content */}
        <div className="relative z-10 space-y-6">
        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5" />
              Research Context
            </CardTitle>
          </CardHeader>

          <CardContent className="space-y-4 text-base leading-relaxed">
            <p>
              This piece of software and the underlying research is part of the
              PhD thesis of <a href='https://www.researchgate.net/profile/Max-Eschenbach' target='_blank' className='text-blue-500 underline'>Max Benjamin Eschenbach</a> at
              the <a href='https://www.dg.architektur.tu-darmstadt.de/fachgebiet_ddu/index.de.jsp' target='_blank' className='text-blue-500 underline'>Digital Design Unit (DDU)</a>
              , supervised and chaired by Prof. Dr.-Ing. Oliver Tessmann, at the <a href='https://www.tu-darmstadt.de/' target='_blank' className='text-blue-500 underline'>Technical University of Darmstadt</a>.
            </p>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Award className="h-5 w-5" />
              Public Funding
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <p>
              Part of this research was conducted within the Project <em><a href='https://www.dg.architektur.tu-darmstadt.de/forschung_ddu/digitale_prozessketten_ddu/computational_design/fertigteil_2__0/fertigteile_2__0.en.jsp' target='_blank' className='text-blue-500 underline'>Fertigteil 2.0 - Real-digital
              process chains for the production of built-in concrete components</a></em>. The project
              <em> Fertigteil 2.0 (Precast Concrete Components 2.0)</em> was funded by the <a href='https://www.bmbf.de/bmbf/en/home/home_node.html' target='_blank' className='text-blue-500 underline'>Federal
              Ministry of Education and Research Germany (BMBF)</a> through the funding
              measure <a href='https://www.remin-kreislaufwirtschaft.de/en/projects/fertigteil-20' target='_blank' className='text-blue-500 underline'>Resource-efficient circular economy - Building and mineral cycles
              (ReMin)</a>.
            </p>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Student Work
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>
                The <code className='bg-accent/40 px-1 py-0.5 rounded'>csc_labels</code> python code to create the QR-Code labels was developed by <a href='https://instagram.com/mirkodutschke' target='_blank' className='text-blue-500 underline'>Mirko Dutschke</a>. The code has
                been refactored as a python module and integrated by Max Benjamin Eschenbach.
              </li>
              <li>
                The <code className='bg-accent/40 px-1 py-0.5 rounded'>csc_sheetscan</code> python module was developed based on the scanning setup
                for sheets that was developed by <a href='https://instagram.com/mirkodutschke' target='_blank' className='text-blue-500 underline'>Mirko Dutschke</a>. The functional code has been written by Max Benjamin Eschenbach.
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Code className="h-5 w-5" />
              Licensing
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>Original code is licensed under the <a href='https://github.com/digitaldesignunit/csc?tab=MIT-1-ov-file' target='_blank' className='text-blue-500 underline'>MIT License</a>.</li>
              <li>
                The <code className='bg-accent/40 px-1 py-0.5 rounded'>csc_sheetscan</code> module makes heavy use of the <a href='https://opencv.org/' target='_blank' className='text-blue-500 underline'>OpenCV</a> library, more specifically its <a href='https://anaconda.org/conda-forge/opencv' target='_blank' className='text-blue-500 underline'>pre-built packages for python</a> via conda-forge.
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ExternalLink className="h-5 w-5" />
              References
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>
                The technical main inspiration for the <em>Catalogue of Second Chances</em> interface is the <a href='https://github.com/ibois-epfl/catalogue-explorer' target='_blank' className='text-blue-500 underline'>Catalogue Explorer</a> by <a href='https://github.com/AymericBr' target='_blank' className='text-blue-500 underline'>@AymbericBr</a>.
              </li>
              <li>
                Another huge inspiration and reference is the <a href='https://epfl-enac.github.io/MANSLAB-IBOIS-EESD-timberstone/' target='_blank' className='text-blue-500 underline'>Timberstone Project</a>, which is the origin of abovementioned Catalogue Explorer.
              </li>
              <li>
                The simple shape descriptors (BoxScore, SphereScore, PlaneScore, LineScore) are computed based on the reference implementation of <a href='https://github.com/keithjlee/DigitalCircularityToolkit' target='_blank' className='text-blue-500 underline'>DigitalCircularityToolkit</a> by <a href='https://github.com/keithjlee' target='_blank' className='text-blue-500 underline'>Keith J. Lee</a>.
              </li>
              <li>
                Huge thanks to <a href='https://sandrosiefert.com/beyond-debris/' target='_blank' className='text-blue-500 underline'>Sandro Siefert</a> for his inspirational work and the contribution of his debris dataset. Looking forward to continue this research with you!
              </li>
            </ul>
          </CardContent>
        </Card>

        <Card className="bg-card/75">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Code className="h-5 w-5" />
              Open Source & Third Party Libraries
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-base leading-relaxed">
            <ul className='list-disc list-inside space-y-2'>
              <li>
                <strong>Frontend Framework:</strong> <a href='https://nextjs.org/' target='_blank' className='text-blue-500 underline'>Next.js</a> - React framework
              </li>
              <li>
                <strong>UI Components:</strong> <a href='https://ui.shadcn.com/' target='_blank' className='text-blue-500 underline'>shadcn/ui</a> - Re-usable React components
              </li>
              <li>
                <strong>3D Graphics:</strong> <a href='https://react-three-fiber.pmnd.rs/' target='_blank' className='text-blue-500 underline'>React Three Fiber</a> & <a href='https://github.com/pmndrs/drei' target='_blank' className='text-blue-500 underline'>Drei</a> - React renderer for Three.js
              </li>
              <li>
                <strong>Styling:</strong> <a href='https://tailwindcss.com/' target='_blank' className='text-blue-500 underline'>Tailwind CSS</a> - CSS framework
              </li>
              <li>
                <strong>Authentication:</strong> <a href='https://next-auth.js.org/' target='_blank' className='text-blue-500 underline'>NextAuth.js</a> - Authentication for Next.js
              </li>
              <li>
                <strong>Database:</strong> <a href='https://www.mongodb.com/' target='_blank' className='text-blue-500 underline'>MongoDB</a> - NoSQL database
              </li>
              <li>
                <strong>Backend Framework:</strong> <a href='https://fastapi.tiangolo.com/' target='_blank' className='text-blue-500 underline'>FastAPI</a> - Python web framework for building APIs
              </li>
              <li>
                <strong>Computer Vision:</strong> <a href='https://opencv.org/' target='_blank' className='text-blue-500 underline'>OpenCV</a> - Computer vision and machine learning library
              </li>
              <li>
                <strong>Mesh Processing:</strong> <a href='https://trimesh.org/' target='_blank' className='text-blue-500 underline'>Trimesh</a> - Python library for loading and using triangular meshes
              </li>
              <li>
                <strong>Scientific Computing:</strong> <a href='https://numpy.org/' target='_blank' className='text-blue-500 underline'>NumPy</a>, <a href='https://scipy.org/' target='_blank' className='text-blue-500 underline'>SciPy</a>, <a href='https://scikit-learn.org/' target='_blank' className='text-blue-500 underline'>scikit-learn</a> - Scientific computing libraries
              </li>
              <li>
                <strong>QR Code Processing:</strong> <a href='https://github.com/Eric-Canas/qreader' target='_blank' className='text-blue-500 underline'>qreader</a> - QR code reader library
              </li>
              <li>
                <strong>Data Validation:</strong> <a href='https://pydantic.dev/' target='_blank' className='text-blue-500 underline'>Pydantic</a> - Data validation using Python type annotations
              </li>
              <li>
                <strong>Icons:</strong> <a href='https://lucide.dev/' target='_blank' className='text-blue-500 underline'>Lucide React</a> - Icon toolkit for React
              </li>
            </ul>
          </CardContent>
        </Card>
        </div>
      </div>
    </div>
  )
}