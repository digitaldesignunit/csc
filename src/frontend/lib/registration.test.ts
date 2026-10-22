/**
 * Who may register without an invitation (decision 8.172): the parsing of the
 * backend's answer and the words of the register page, the sign-in form, the
 * sidebar and the admin users page for both modes.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  codeFieldLabel,
  domainList,
  OPEN_DOMAINS_HINT,
  openDomainsHelp,
  parseRegistration,
  registerLinkText,
  registrationSummary,
  signInAlternativeText,
  signInButtonText,
  signInRegisterPrompt,
} from './registration'

const OPEN = { openDomains: ['a.example', 'b.example'], inviteOnly: false }
const CLOSED = { openDomains: [], inviteOnly: true }

test('the answer of the backend is read, anything else is not an answer', () => {
  assert.deepEqual(parseRegistration({ open_domains: [], invite_only: true }), CLOSED)
  assert.deepEqual(parseRegistration({ open_domains: ['a.example', 'b.example'], invite_only: false }), OPEN)
  assert.deepEqual(parseRegistration({ open_domains: [' a.example ', ''], invite_only: false }),
    { openDomains: ['a.example'], inviteOnly: false })
  // the domains decide, whatever the flag says
  assert.equal(parseRegistration({ open_domains: [''], invite_only: false })?.inviteOnly, true)
  assert.equal(parseRegistration({ open_domains: ['a.example'], invite_only: true })?.inviteOnly, false)
  for (const bad of [null, undefined, 'x', 3, {}, { open_domains: 'a.example' }, { open_domains: [1] }]) {
    assert.equal(parseRegistration(bad), null, String(bad))
  }
})

test('the domains read as a list', () => {
  assert.equal(domainList([]), '')
  assert.equal(domainList(['a.example']), 'a.example')
  assert.equal(domainList(['a.example', 'b.example']), 'a.example and b.example')
  assert.equal(domainList(['a.example', 'b.example', 'c.example']), 'a.example, b.example and c.example')
})

test('the open page names the domains in the tooltip, not in the hint', () => {
  assert.equal(OPEN_DOMAINS_HINT, 'Registration is open only to addresses of certain domains')
  const help = openDomainsHelp(OPEN.openDomains)
  assert.ok(help.includes('a.example and b.example'))
  assert.ok(help.includes('these domains'))
  assert.ok(openDomainsHelp(['a.example']).includes('this domain'))
  assert.ok(!/darmstadt/i.test(OPEN_DOMAINS_HINT + help + codeFieldLabel(OPEN, false)))
})

test('the code field is labelled for addresses outside the open domains', () => {
  assert.equal(codeFieldLabel(OPEN, false), 'Invitation code (for addresses outside these domains)')
  assert.equal(codeFieldLabel(OPEN, true), 'Invitation code')
  assert.equal(codeFieldLabel(CLOSED, false), 'Invitation code')
  assert.equal(codeFieldLabel(null, false), 'Invitation code (optional)')
})

test('the links use words that fit the mode', () => {
  assert.equal(registerLinkText(CLOSED), 'Have an invitation?')
  assert.equal(registerLinkText(OPEN), 'Register')
  assert.equal(registerLinkText(null), null)
  assert.equal(signInRegisterPrompt(OPEN), "Don't have an account?")
  assert.equal(signInRegisterPrompt(CLOSED), 'No account yet?')
  assert.equal(signInAlternativeText(CLOSED), 'or use an invitation')
  assert.equal(signInAlternativeText(OPEN), 'or register')
  assert.equal(signInButtonText(CLOSED), 'Sign in')
  assert.equal(signInButtonText(OPEN), 'Sign in / Register')
  assert.equal(signInButtonText(null), 'Sign in')
  // unknown mode (server render, fetch under way or failed): nothing suggests open registration
  assert.equal(signInRegisterPrompt(null), null)
  assert.equal(signInAlternativeText(null), null)
})

test('the admin users page says who may register', () => {
  assert.equal(registrationSummary(CLOSED), 'Registration is by invitation only.')
  assert.ok(registrationSummary(OPEN).includes('a.example and b.example'))
  assert.ok(registrationSummary(null).includes('invitation'))
})
