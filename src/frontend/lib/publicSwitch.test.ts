import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  PUBLIC_EXPOSES,
  canSwitchPublic,
  datasetPublicHelp,
  datasetPublicLabel,
  publicConfirmText,
} from './publicSwitch'

test('a moderator always, the creator only while nothing was published', () => {
  assert.equal(canSwitchPublic({ moderates: true, isCreator: false, everPublished: true }), true)
  assert.equal(canSwitchPublic({ moderates: false, isCreator: true, everPublished: false }), true)
  assert.equal(canSwitchPublic({ moderates: false, isCreator: true, everPublished: true }), false)
  assert.equal(canSwitchPublic({ moderates: false, isCreator: false, everPublished: false }), false)
})

test('the confirmation names what a visitor without an account sees', () => {
  const text = publicConfirmText('This piece becomes public.')
  assert.match(text, /^This piece becomes public\. Anyone without an account then sees: /)
  assert.match(text, /photos/)
  assert.match(text, /organisations only, no people/)
  assert.match(text, /sign in to download/)
  assert.equal(PUBLIC_EXPOSES.length, 3)
})

test('the dataset action shows the number it affects', () => {
  assert.equal(datasetPublicLabel(true, null), 'Make all published pieces public')
  assert.equal(datasetPublicLabel(false, 12), 'Make all published pieces private (12)')
  assert.equal(datasetPublicHelp(null, true), 'Counting...')
  assert.equal(datasetPublicHelp(0, true), 'No published piece is private.')
  assert.equal(datasetPublicHelp(0, false), 'No published piece is public.')
  assert.match(datasetPublicHelp(1, true), /^1 published piece would become public\./)
  assert.match(datasetPublicHelp(7, false), /^7 published pieces would become private\. Unpublished and withdrawn/)
})
