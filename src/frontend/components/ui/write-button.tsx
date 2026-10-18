'use client'

import * as React from 'react'

import { Button } from '@/components/ui/button'
import { useReadOnly } from '@/components/common/ReadOnlyProvider'
import { READ_ONLY_TITLE } from '@/lib/readOnly'

/**
 * A button that changes data. While the backend is read-only (maintenance,
 * decision 8.154) it is disabled and says why; otherwise it is a plain Button.
 * Every button that submits, saves, uploads, deletes or invites uses this one.
 */
function WriteButton({ disabled, title, ...props }: React.ComponentProps<typeof Button>) {
  const readOnly = useReadOnly()
  return (
    <Button
      {...props}
      disabled={disabled || readOnly}
      title={readOnly ? READ_ONLY_TITLE : title}
    />
  )
}

export { WriteButton }
