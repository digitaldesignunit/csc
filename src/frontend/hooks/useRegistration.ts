'use client'

/**
 * The registration mode of the backend (decision 8.172), fetched once per page
 * load and shared by every component that asks (register page, sign-in form,
 * sidebar, admin users page). A failed fetch is not kept: the next ask retries.
 */
import { useEffect, useState } from 'react'

import { parseRegistration, REGISTRATION_URL, type RegistrationInfo } from '@/lib/registration'

let pending: Promise<RegistrationInfo | null> | null = null

function load(): Promise<RegistrationInfo | null> {
  if (!pending) {
    pending = fetch(REGISTRATION_URL)
      .then((res) => (res.ok ? res.json() : null))
      .then(parseRegistration)
      .catch(() => null)
      .then((info) => {
        if (!info) pending = null
        return info
      })
  }
  return pending
}

/**
 * `info` is null until the answer is in, and stays null when the backend does not answer.
 * `enabled` false asks nothing (a signed-in visitor needs no register link).
 */
export function useRegistration(enabled = true): { info: RegistrationInfo | null; ready: boolean } {
  const [state, setState] = useState<{ info: RegistrationInfo | null; ready: boolean }>({
    info: null,
    ready: false,
  })
  useEffect(() => {
    if (!enabled) return
    let alive = true
    void load().then((info) => {
      if (alive) setState({ info, ready: true })
    })
    return () => {
      alive = false
    }
  }, [enabled])
  return state
}
