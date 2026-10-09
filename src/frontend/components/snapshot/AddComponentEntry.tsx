'use client'

/**
 * `/add-component`: pick what is being recorded (a new component or a piece
 * cut from others), unless the link already says, then the snapshot form.
 */
import { useState } from 'react'
import { PackagePlus, Scissors } from 'lucide-react'

import { Button } from '@/components/ui/button'
import SnapshotForm from './SnapshotForm'

type Choice = 'new' | 'cut'

export default function AddComponentEntry({
  tag,
  parents,
  initialMode,
}: {
  tag?: string
  parents: string[]
  initialMode: Choice | null
}) {
  const [mode, setMode] = useState<Choice | null>(initialMode)

  if (!mode) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">What are you recording?</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Button type="button" variant="outline" className="h-auto justify-start gap-3 whitespace-normal p-4 text-left"
            onClick={() => setMode('new')}>
            <PackagePlus className="h-5 w-5 shrink-0" />
            <span>
              <span className="block font-medium">New component</span>
              <span className="block text-xs font-normal text-muted-foreground">
                A piece with a tag that is not in the catalog yet.
              </span>
            </span>
          </Button>
          <Button type="button" variant="outline" className="h-auto justify-start gap-3 whitespace-normal p-4 text-left"
            onClick={() => setMode('cut')}>
            <Scissors className="h-5 w-5 shrink-0" />
            <span>
              <span className="block font-medium">Cut from pieces</span>
              <span className="block text-xs font-normal text-muted-foreground">
                A piece cut from one component, or merged from several.
              </span>
            </span>
          </Button>
        </div>
      </div>
    )
  }
  return <SnapshotForm key={mode} mode={mode} tag={tag} parents={mode === 'cut' ? parents : undefined} />
}
