/**
 * The checks of the profile form (decision 8.133): the same rules as the API.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  actorFromProfile,
  checkOrcid,
  checkRor,
  orcidCheckDigit,
  problemField,
  profileFields,
  profilePatch,
  profileProblems,
  roleOf,
} from '@/lib/profile'

test('an ORCID is read from the id, the id without hyphens and the URL', () => {
  for (const text of ['0000-0002-1825-0097', '0000000218250097', 'https://orcid.org/0000-0002-1825-0097',
    ' http://orcid.org/0000-0002-1825-0097 ']) {
    assert.deepEqual(checkOrcid(text), { ok: true, value: '0000-0002-1825-0097' }, text)
  }
  assert.deepEqual(checkOrcid(''), { ok: true, value: null })
  assert.deepEqual(checkOrcid('0000-0002-1694-233x'), { ok: true, value: '0000-0002-1694-233X' })
})

test('an ORCID with the wrong shape or check digit is refused with a message', () => {
  assert.deepEqual(checkOrcid('0000-0002-1825-0098'), { ok: false, message: 'This ORCID has a wrong check digit.' })
  assert.deepEqual(checkOrcid('1234'), { ok: false, message: 'An ORCID looks like 0000-0002-1825-0097.' })
  assert.equal(checkOrcid('abc').ok, false)
})

test('the check digit is ISO 7064 MOD 11-2', () => {
  assert.equal(orcidCheckDigit('000000021825009'), '7')
  assert.equal(orcidCheckDigit('000000021694233'), 'X')
})

test('a ROR id is read from the id and the URL', () => {
  for (const text of ['03abcde12', 'https://ror.org/03abcde12', 'ror.org/03abcde12'.replace('ror.org', 'https://ror.org'),
    'https://ror.org/03ABCDE12/']) {
    assert.deepEqual(checkRor(text), { ok: true, value: 'https://ror.org/03abcde12' }, text)
  }
  assert.deepEqual(checkRor(''), { ok: true, value: null })
  assert.equal(checkRor('13abcde12').ok, false)           // starts with 0
  assert.equal(checkRor('03abcdi12').ok, false)           // no i in the alphabet
  assert.equal(checkRor('03abcde1').ok, false)
})

test('the profile problems are named per field and an empty optional field is fine', () => {
  const fields = { full_name: 'Ada', organization: '', organization_ror: '', orcid: '', default_role: 'operator' as const }
  assert.deepEqual(profileProblems(fields), {})
  const bad = profileProblems({ ...fields, full_name: '  ', orcid: '0000-0002-1825-0098', organization_ror: 'x' })
  assert.deepEqual(Object.keys(bad).sort(), ['full_name', 'orcid', 'organization_ror'])
  assert.deepEqual(profileProblems({ ...fields, organization: 'x'.repeat(201) }), { organization: 'At most 200 characters.' })
})

test('the patch holds only the fields that changed, trimmed', () => {
  const stored = { full_name: 'Ada', organization: 'Lab', orcid: null, default_role: 'laboratory' }
  const fields = { ...profileFields(stored), organization: ' Lab GmbH ', orcid: '0000-0002-1825-0097' }
  assert.deepEqual(profilePatch(fields, stored), { organization: 'Lab GmbH', orcid: '0000-0002-1825-0097' })
  assert.deepEqual(profilePatch(profileFields(stored), stored), {})
  // an emptied field is sent as an empty text (the API clears it)
  assert.deepEqual(profilePatch({ ...profileFields(stored), organization: '' }, stored), { organization: '' })
})

test('the API messages are matched to a field', () => {
  assert.equal(problemField('an ORCID looks like 0000-0002-1825-0097'), 'orcid')
  assert.equal(problemField('this ORCID has a wrong check digit'), 'orcid')
  assert.equal(problemField('a ROR id looks like 03abcde12 (https://ror.org/...)'), 'organization_ror')
  assert.equal(problemField('the name cannot be empty'), 'full_name')
  assert.equal(problemField('something else'), null)
})

test('the role falls back to operator', () => {
  assert.equal(roleOf('laboratory'), 'laboratory')
  assert.equal(roleOf('president'), 'operator')
  assert.equal(roleOf(null), 'operator')
})

test('"Add me" copies the profile into an actor of kind user', () => {
  const actor = actorFromProfile({
    _id: 'u1', username: 'ada', full_name: ' Ada Lovelace ', organization: 'Lab GmbH',
    organization_ror: 'https://ror.org/03abcde12', orcid: '0000-0002-1825-0097', default_role: 'laboratory',
  })
  assert.deepEqual(actor, {
    kind: 'user', user_id: 'u1', name: 'Ada Lovelace', role: 'laboratory', organization: 'Lab GmbH',
    organization_ror: 'https://ror.org/03abcde12', orcid: '0000-0002-1825-0097',
  })
  // a bare profile: the username stands in for the name, nothing else is invented
  assert.deepEqual(actorFromProfile({ _id: 'u2', username: 'bob' }), {
    kind: 'user', user_id: 'u2', name: 'bob', role: 'operator',
  })
})
