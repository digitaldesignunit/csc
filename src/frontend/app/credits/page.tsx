import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'

export default function CreditsPage() {
  return (
    <div className='grid gap-[32px] m-4'>
      <Card>
        <CardHeader>
          <CardTitle>Credits</CardTitle>
          <CardDescription>Credits, Sources & References for the <em>Catalogue of Second Chances</em></CardDescription>
        </CardHeader>

        <CardContent>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Context</h2>
            <p className='mb-4'>
              This piece of software and the underlying research is part of the
              PhD thesis of <a href='https://www.researchgate.net/profile/Max-Eschenbach' target='_blank' className='text-blue-500 underline'>Max Benjamin Eschenbach</a> at
              the <a href='https://www.dg.architektur.tu-darmstadt.de/fachgebiet_ddu/index.de.jsp' target='_blank' className='text-blue-500 underline'>Digital Design Unit (DDU)</a>
              , <a href='https://www.tu-darmstadt.de/' target='_blank' className='text-blue-500 underline'>Technical University of Darmstadt</a>.
              DDU is chaired by Prof. Dr.-Ing. Oliver Tessmann, who is also the
              supervisor of the PhD Thesis.
            </p>
          </section>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Public Funding</h2>
            <p className='mb-4'>
              Part of this research was conducted within the Project <em><a href='https://www.dg.architektur.tu-darmstadt.de/forschung_ddu/digitale_prozessketten_ddu/computational_design/fertigteil_2__0/fertigteile_2__0.en.jsp' target='_blank' className='text-blue-500 underline'>Fertigteil 2.0 - Real-digital
              process chains for the production of built-in concrete components</a></em>. The project
              <em> Fertigteil 2.0 (Precast Concrete Components 2.0)</em> was funded by the <a href='https://www.bmbf.de/bmbf/en/home/home_node.html' target='_blank' className='text-blue-500 underline'>Federal
              Ministry of Education and Research Germany (BMBF)</a> through the funding
              measure <a href='https://www.remin-kreislaufwirtschaft.de/en/projects/fertigteil-20' target='_blank' className='text-blue-500 underline'>Resource-efficient circular economy - Building and mineral cycles
              (ReMin)</a>.
            </p>
          </section>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Student Work</h2>
            <ul className='list-disc list-inside mb-4'>
              <li>
                The <code className='bg-gray-200 px-1 py-0.5 rounded'>csc_labels</code> python code to create the QR-Code labels was developed by Mirko Dutschke. The code has
                been refactored as a python module and integrated by Max Benjamin Eschenbach.
              </li>
              <li>
                The <code className='bg-gray-200 px-1 py-0.5 rounded'>csc_sheetscan</code> python module was developed based on the scanning setup
                for sheets that was developed by Mirko Dutschke. The functional code has been
                written by Max Benjamin Eschenbach.
              </li>
            </ul>
          </section>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Licensing</h2>
            <ul className='list-disc list-inside mb-4'>
              <li>Original code is licensed under the <a href='https://github.com/digitaldesignunit/csc?tab=MIT-1-ov-file' target='_blank' className='text-blue-500 underline'>MIT License</a>.</li>
              <li>
                The <code className='bg-gray-200 px-1 py-0.5 rounded'>csc_sheetscan</code> module makes heavy use of the <a href='https://opencv.org/' target='_blank' className='text-blue-500 underline'>OpenCV</a> library, more specifically its <a href='https://anaconda.org/conda-forge/opencv' target='_blank' className='text-blue-500 underline'>pre-built packages for python</a> via conda-forge.
              </li>
            </ul>
          </section>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>References</h2>
            <ul className='list-disc list-inside mb-4'>
              <li>
                The technical main inspiration for the <em>Catalogue of Second Chances</em> interface is the <a href='https://github.com/ibois-epfl/catalogue-explorer' target='_blank' className='text-blue-500 underline'>Catalogue Explorer</a> by <a href='https://github.com/AymericBr' target='_blank' className='text-blue-500 underline'>@AymbericBr</a>.
              </li>
              <li>
                Another huge inspiration and reference is the <a href='https://epfl-enac.github.io/MANSLAB-IBOIS-EESD-timberstone/' target='_blank' className='text-blue-500 underline'>Timberstone Project</a>, which is the origin of abovementioned Catalogue Explorer.
              </li>
            </ul>
          </section>

          <section className='mb-8'>
            <h2 className='text-xl font-bold mb-4'>Open Source & Third Party Libraries</h2>
            <ul className='list-disc list-inside mb-4'>
              <li>
                ...
              </li>
              <li>
                ...
              </li>
            </ul>
          </section>
        
        </CardContent>
      
      </Card>
    </div>
  )
}