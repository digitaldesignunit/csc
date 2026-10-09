import assert from 'node:assert/strict'
import { test } from 'node:test'

import { datasetCounts } from './datasets'

test('the counts line names members and components', () => {
  assert.equal(datasetCounts({ member_count: 3, component_count: 120 }), '3 members, 120 components')
  assert.equal(datasetCounts({ member_count: 1, component_count: 1 }), '1 member, 1 component')
  assert.equal(datasetCounts({ member_count: 0, component_count: 0 }), '0 members, 0 components')
})

test('a count that is not there is left out', () => {
  assert.equal(datasetCounts({ component_count: 2 }), '2 components')
  assert.equal(datasetCounts({ member_count: null, component_count: 1500 }), '1,500 components')
  assert.equal(datasetCounts({}), '')
})
