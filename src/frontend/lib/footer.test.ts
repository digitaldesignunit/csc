import assert from 'node:assert/strict'
import { test } from 'node:test'

import { footerMode } from './footer'

const ID = '2e6f6e3c-165f-4ca2-9be9-884e6e8e84f5'

test('the public pages have the full footer', () => {
  for (const path of ['/', '/auth/signin', '/auth/register', '/credits', '/imprint']) {
    assert.equal(footerMode(path, false), 'full', path)
    assert.equal(footerMode(path, true), 'full', path)
  }
})

test('Browse and a component page are public for a visitor and app pages for a member', () => {
  for (const path of ['/components', `/components/${ID}`]) {
    assert.equal(footerMode(path, false), 'full', path)
    assert.equal(footerMode(path, true), 'thin', path)
  }
})

test('the other pages of the app have the thin line', () => {
  for (const path of ['/components/map', '/analytics', '/my-work', '/scan', '/settings', '/admin/validation', '/gh-interface']) {
    assert.equal(footerMode(path, true), 'thin', path)
    assert.equal(footerMode(path, false), 'thin', path)
  }
})

test('a form has none', () => {
  for (const path of ['/add-component', `/components/${ID}/snapshot/new`, `/components/${ID}/evidence/new`, `/components/${ID}/edit`]) {
    assert.equal(footerMode(path, true), 'none', path)
  }
})

test('a trailing slash does not change the answer', () => {
  assert.equal(footerMode('/components/', false), 'full')
  assert.equal(footerMode('/add-component/', true), 'none')
})
