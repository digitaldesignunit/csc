import assert from 'node:assert/strict'
import { test } from 'node:test'

import { allowsAnonymousCatalogRead } from './publicAccess'

test('an anonymous visitor reads the Grasshopper page and its screenshots, nothing else under it', () => {
  assert.equal(allowsAnonymousCatalogRead('/gh-interface', 'GET'), true)
  assert.equal(allowsAnonymousCatalogRead('/gh-interface/csc_session.jpg', 'GET'), true)
  assert.equal(allowsAnonymousCatalogRead('/gh-interface/csc_fetchsnapshot.PNG', 'HEAD'), true)
  assert.equal(allowsAnonymousCatalogRead('/gh-interface/csc_session.jpg', 'POST'), false)
  assert.equal(allowsAnonymousCatalogRead('/gh-interface/secret.json', 'GET'), false)
  assert.equal(allowsAnonymousCatalogRead('/gh-interface/../admin/x.jpg', 'GET'), false)
})

test('the other pages stay behind the sign-in', () => {
  assert.equal(allowsAnonymousCatalogRead('/my-work', 'GET'), false)
  assert.equal(allowsAnonymousCatalogRead('/admin/validation', 'GET'), false)
  assert.equal(allowsAnonymousCatalogRead('/components/map', 'GET'), true)
})
