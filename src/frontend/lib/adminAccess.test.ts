import assert from 'node:assert/strict'
import { test } from 'node:test'

import { adminPageNeed } from './adminAccess'

test('each admin page names who may open it', () => {
  assert.equal(adminPageNeed('/admin'), 'admin')
  assert.equal(adminPageNeed('/admin/users'), 'admin')
  assert.equal(adminPageNeed('/admin/materials'), 'admin')
  assert.equal(adminPageNeed('/admin/geometry'), 'admin')
  assert.equal(adminPageNeed('/admin/logs'), 'admin')
  assert.equal(adminPageNeed('/admin/datasets'), 'moderator')
  assert.equal(adminPageNeed('/admin/datasets/later_dataset'), 'moderator')
  assert.equal(adminPageNeed('/admin/validation'), 'moderator-or-reviewer')
  assert.equal(adminPageNeed('/admin/review'), 'moderator-or-reviewer')
})
