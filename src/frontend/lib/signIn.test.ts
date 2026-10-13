/**
 * The web sign-in exchanges the credentials with the backend only (8.144 f):
 * a 401 or 403 is a failed sign-in, and nothing the visitor typed is logged.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import { signInWithBackend, type SignInDeps } from './signIn'

const b64 = (value: object) => Buffer.from(JSON.stringify(value)).toString('base64url')
const jwt = (exp: number) => `${b64({ alg: 'HS256' })}.${b64({ sub: 'u1', exp })}.sig`

type Call = { url: string; init: RequestInit }

function setup(answers: Array<Response | Error>) {
  const calls: Call[] = []
  const logs: string[] = []
  const deps: SignInDeps = {
    fetch: (async (url: unknown, init?: RequestInit) => {
      calls.push({ url: String(url), init: init ?? {} })
      const answer = answers.shift()
      if (answer instanceof Error) throw answer
      return answer as Response
    }) as typeof fetch,
    backendUrl: 'http://backend.test/',
    headers: { 'X-CSC-Client': 'web' },
    log: (message) => logs.push(message),
    now: () => 1_000_000,
  }
  return { deps, calls, logs }
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const ME = { _id: 'u1', username: 'sample-user', full_name: 'Sample User', email: 'sample@example.org', role: 'user' }

test('the credentials go to /auth/token only, with the client header', async () => {
  const exp = 2_000_000_000
  const { deps, calls } = setup([json(200, { access_token: jwt(exp) }), json(200, ME)])
  const user = await signInWithBackend({ identifier: '  Sample@Example.org ', password: 'pw-1' }, deps)
  assert.equal(calls[0].url, 'http://backend.test/auth/token')
  assert.equal(calls[0].init.method, 'POST')
  const sent = calls[0].init.body as URLSearchParams
  assert.equal(sent.get('username'), 'Sample@Example.org')   // the backend lower-cases
  assert.equal(sent.get('password'), 'pw-1')
  assert.equal((calls[0].init.headers as Record<string, string>)['X-CSC-Client'], 'web')
  assert.equal(calls[1].url, 'http://backend.test/users/me')
  assert.match((calls[1].init.headers as Record<string, string>).Authorization, /^Bearer /)
  assert.deepEqual(
    { id: user?.id, username: user?.username, role: user?.role, name: user?.name, email: user?.email },
    { id: 'u1', username: 'sample-user', role: 'user', name: 'Sample User', email: 'sample@example.org' })
  assert.equal(user?.apiTokenExpiresAt, exp * 1000)
})

test('401 and 403 are a failed sign-in, 429 too', async () => {
  for (const status of [401, 403, 429, 500]) {
    const { deps, calls } = setup([json(status, { detail: 'no' })])
    assert.equal(await signInWithBackend({ identifier: 'a', password: 'b' }, deps), null)
    assert.equal(calls.length, 1, 'no profile call after a refusal')
  }
})

test('an unreachable backend is a failed sign-in', async () => {
  const { deps } = setup([new Error('connect ECONNREFUSED')])
  assert.equal(await signInWithBackend({ identifier: 'a', password: 'b' }, deps), null)
})

test('no usable credentials: nothing is sent', async () => {
  const { deps, calls } = setup([])
  assert.equal(await signInWithBackend(undefined, deps), null)
  assert.equal(await signInWithBackend({ identifier: 'a' }, deps), null)
  assert.equal(await signInWithBackend({ identifier: 5, password: 'b' }, deps), null)
  assert.equal(calls.length, 0)
})

test('the log never holds what the visitor typed or the profile', async () => {
  const typed = 'typed-identifier@example.org'
  const secret = 'secret-pw-value'
  const runs = [
    [json(401, { detail: 'Incorrect username/email or password' })],
    [json(403, { detail: 'Email not verified' })],
    [new Error(`connect failed for ${typed}`)],
    [json(200, { access_token: jwt(2_000_000_000) }), json(200, ME)],
  ]
  for (const answers of runs) {
    const { deps, logs } = setup(answers as Array<Response | Error>)
    await signInWithBackend({ identifier: typed, password: secret }, deps)
    assert.ok(logs.length > 0, 'the outcome is logged')
    const text = logs.join('\n')
    assert.ok(!text.includes(typed) && !text.includes(secret), text)
    assert.ok(!text.includes('sample@example.org') && !text.includes('sample-user'), text)
  }
})
