'use client'

/**
 * The consent of a connection (decision 8.168 b). A tool such as Claude sends
 * the browser here from `/authorize` with the id of its request; the card shows
 * the host Allow sends you to, the access, and Allow / Deny. Nothing is
 * remembered. Signed out, the proxy sends the visitor to the sign-in page and
 * back here with the same link. After the answer the browser goes to the
 * address the backend built from the redirect URI it validated, checked once
 * more by `safeReturnUrl`.
 */
import { Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'

import ConsentCard from '@/components/oauth/ConsentCard'
import { BackendError, backendJson } from '@/lib/backend'
import {
  GONE_TEXT,
  requestId,
  safeReturnUrl,
  type ConsentResult,
  type ConsentView,
} from '@/lib/oauthConsent'

function ConsentContent() {
  const params = useSearchParams()
  const id = requestId(params.get('request'))
  const [view, setView] = useState<ConsentView | null>(null)
  const [problem, setProblem] = useState<string | null>(id ? null : GONE_TEXT)
  const [busy, setBusy] = useState(false)
  const [leaving, setLeaving] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    let cancelled = false
    backendJson<ConsentView>(`/oauth/requests/${encodeURIComponent(id)}`)
      .then((body) => { if (!cancelled) setView(body) })
      .catch((err) => {
        if (!cancelled) setProblem(err instanceof BackendError && err.status === 404 ? GONE_TEXT : (err as Error).message)
      })
    return () => { cancelled = true }
  }, [id])

  const decide = async (allow: boolean) => {
    if (!id || busy) return
    setBusy(true)
    setProblem(null)
    try {
      const answer = await backendJson<ConsentResult>(
        `/oauth/requests/${encodeURIComponent(id)}/decision`, { method: 'POST', body: { allow } })
      const target = safeReturnUrl(answer.redirect_to)
      if (!target) {
        setProblem('The answer could not be sent back to the tool.')
        return
      }
      setLeaving(view?.redirect_host ?? '')
      window.location.assign(target)
    } catch (err) {
      setProblem(err instanceof BackendError && err.status === 404 ? GONE_TEXT : (err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <ConsentCard
      view={view}
      problem={problem}
      busy={busy}
      leaving={leaving}
      onAllow={() => decide(true)}
      onDeny={() => decide(false)}
    />
  )
}

export default function ConsentPage() {
  return (
    <Suspense fallback={null}>
      <ConsentContent />
    </Suspense>
  )
}
