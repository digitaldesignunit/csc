/**
 * The read-only state in the interface (decision 8.154): the banner shows the
 * text, and a WriteButton is disabled, with its reason, only while the state is on.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { ReadOnlyBanner, ReadOnlyContext } from '../components/common/ReadOnlyProvider'
import { WriteButton } from '../components/ui/write-button'
import { READ_ONLY_BANNER, READ_ONLY_TITLE } from './readOnly'

const within = (value: boolean, child: ReturnType<typeof createElement>) =>
  renderToStaticMarkup(createElement(ReadOnlyContext.Provider, { value }, child))

test('the banner shows its text only while the catalog is read-only', () => {
  assert.ok(within(true, createElement(ReadOnlyBanner)).includes(READ_ONLY_BANNER))
  assert.equal(within(false, createElement(ReadOnlyBanner)), '')
})

test('a write button is disabled with its reason while read-only, and plain otherwise', () => {
  const on = within(true, createElement(WriteButton, null, 'Save'))
  assert.match(on, /disabled=""/)
  assert.ok(on.includes(`title="${READ_ONLY_TITLE}"`))
  const off = within(false, createElement(WriteButton, { title: 'Save it' }, 'Save'))
  assert.ok(!/ disabled=""/.test(off))
  assert.ok(off.includes('title="Save it"'))
  // its own disabled stays
  assert.match(within(false, createElement(WriteButton, { disabled: true }, 'Save')), /disabled=""/)
})
