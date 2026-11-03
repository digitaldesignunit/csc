/**
 * Beta notice (issue #52): the version in the banner and the login notice comes
 * from package.json, through the {version} placeholder of the text.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'

import pkg from '../package.json'
import {
  BETA_VERSION_PLACEHOLDER,
  fillBetaVersion,
  getBetaBannerText,
  getBetaLoginMessage,
} from './beta'

const KEYS = ['BETA_BANNER_TEXT', 'BETA_LOGIN_MESSAGE'] as const
const saved = Object.fromEntries(KEYS.map((key) => [key, process.env[key]]))

afterEach(() => {
  for (const key of KEYS) {
    if (saved[key] === undefined) delete process.env[key]
    else process.env[key] = saved[key]
  }
})

test('the placeholder is replaced by the version of package.json', () => {
  assert.equal(BETA_VERSION_PLACEHOLDER, '{version}')
  assert.match(pkg.version, /^\d+\.\d+\.\d+\.\d+/)
  assert.equal(fillBetaVersion('VERSION {version}'), `VERSION ${pkg.version}`)
  assert.equal(
    fillBetaVersion('testing {version}, then {version} again'),
    `testing ${pkg.version}, then ${pkg.version} again`,
  )
  assert.equal(fillBetaVersion('VERSION {version}', '1.2.3.4'), 'VERSION 1.2.3.4')
})

test('a text without the placeholder stays as it is', () => {
  assert.equal(fillBetaVersion('VERSION 0.1.0.0'), 'VERSION 0.1.0.0')
  assert.equal(fillBetaVersion('Beta {Version} {ver}'), 'Beta {Version} {ver}')
  assert.equal(fillBetaVersion(''), '')
})

test('the banner and the login notice fill the placeholder of the environment', () => {
  process.env.BETA_BANNER_TEXT = '"VERSION {version}"'
  process.env.BETA_LOGIN_MESSAGE = 'In testing for version {version}! Thank you.'
  assert.equal(getBetaBannerText(), `VERSION ${pkg.version}`)
  assert.equal(getBetaLoginMessage(), `In testing for version ${pkg.version}! Thank you.`)
})

test('an environment text without the placeholder is shown unchanged', () => {
  process.env.BETA_BANNER_TEXT = 'VERSION 0.5.0.0'
  process.env.BETA_LOGIN_MESSAGE = 'Testing 0.5.0.0.'
  assert.equal(getBetaBannerText(), 'VERSION 0.5.0.0')
  assert.equal(getBetaLoginMessage(), 'Testing 0.5.0.0.')
})

test('the defaults name the version through the placeholder', () => {
  delete process.env.BETA_BANNER_TEXT
  delete process.env.BETA_LOGIN_MESSAGE
  assert.equal(getBetaBannerText(), `Beta ${pkg.version}`)
  assert.ok(getBetaLoginMessage().includes(`(version ${pkg.version})`))
  assert.ok(!getBetaLoginMessage().includes('{version}'))
})
