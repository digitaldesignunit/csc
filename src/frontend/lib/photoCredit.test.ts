import assert from 'node:assert/strict'
import { test } from 'node:test'

import { creditDisplayText, creditFromInputs, creditInputProblem, creditToShow } from './photoCredit'

test('a credit is shown trimmed, and its link only when it is a web address', () => {
  assert.deepEqual(creditToShow({ text: ' Photo: archive ', url: ' https://x.org/a ' }),
    { text: 'Photo: archive', url: 'https://x.org/a' })
  assert.deepEqual(creditToShow({ text: 'Photo', url: 'javascript:alert(1)' }), { text: 'Photo', url: null })
  assert.deepEqual(creditToShow({ text: 'Photo' }), { text: 'Photo', url: null })
  assert.equal(creditToShow({ text: '  ', url: 'https://x.org' }), null)
  assert.equal(creditToShow(null), null)
  assert.equal(creditToShow(undefined), null)
  assert.equal(creditToShow('Photo'), null)
})

test('the copyright sign is written for (c)', () => {
  assert.equal(creditDisplayText('Photo: (c) Example Catalogue (catalogue.example)'),
    'Photo: \u00a9 Example Catalogue (catalogue.example)')
  assert.equal(creditDisplayText('Photo: (C) X'), 'Photo: \u00a9 X')
  assert.equal(creditDisplayText('no sign'), 'no sign')
})

test('the edit inputs make the PATCH value: no text clears the credit', () => {
  assert.deepEqual(creditFromInputs(' Own photo ', ' '), { text: 'Own photo', url: null })
  assert.deepEqual(creditFromInputs('Photo', ' https://x.org '), { text: 'Photo', url: 'https://x.org' })
  assert.equal(creditFromInputs('  ', ''), null)
})

test('the inputs are checked before they are sent', () => {
  assert.equal(creditInputProblem('', ''), '')
  assert.equal(creditInputProblem('Photo', ''), '')
  assert.equal(creditInputProblem('Photo', 'https://x.org'), '')
  assert.match(creditInputProblem('', 'https://x.org'), /credit text/)
  assert.match(creditInputProblem('Photo', 'ftp://x.org'), /http/)
  assert.match(creditInputProblem('x'.repeat(301), ''), /300/)
})
