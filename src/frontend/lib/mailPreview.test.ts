import assert from 'node:assert/strict'
import test from 'node:test'

import { PREVIEW_WIDTHS, forcedDark, previewHtml, testFailure } from '@/lib/mailPreview'

const HTML = '<style>@media (prefers-color-scheme: dark) { .a { color: #fff } }</style><p class="a">x</p>'

test('the dark preview makes the dark block unconditional', () => {
  assert.ok(!forcedDark(HTML).includes('prefers-color-scheme'))
  assert.ok(forcedDark(HTML).includes('@media all'))
  assert.equal(previewHtml(HTML, 'light'), HTML)
  assert.equal(previewHtml(HTML, 'dark'), forcedDark(HTML))
})

test('a mail without a dark block is left as it is', () => {
  assert.equal(forcedDark('<p>x</p>'), '<p>x</p>')
})

test('a phone is narrower than a desktop client', () => {
  assert.ok(PREVIEW_WIDTHS.phone < PREVIEW_WIDTHS.desktop)
})

test('a failed send shows the reason when there is one', () => {
  assert.equal(testFailure(new Error('The mail was not sent: refused')), 'The mail was not sent: refused')
  assert.match(testFailure(null), /could not be sent/)
})
