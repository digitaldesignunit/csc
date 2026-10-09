import assert from 'node:assert/strict'
import { test } from 'node:test'

import { THUMB_BOX, THUMB_IMG, THUMB_WRAP_LIMIT, thumbRow } from './photoThumbs'

test('a few photos wrap in the card, many scroll inside it', () => {
  assert.match(thumbRow(1), /flex-wrap/)
  assert.match(thumbRow(THUMB_WRAP_LIMIT), /flex-wrap/)
  assert.match(thumbRow(THUMB_WRAP_LIMIT + 1), /overflow-x-auto/)
  assert.doesNotMatch(thumbRow(THUMB_WRAP_LIMIT + 1), /flex-wrap/)
})

test('a thumbnail has a fixed height and a width that follows the photo, clamped', () => {
  assert.match(THUMB_BOX, /h-\[var\(--th\)\]/)
  assert.match(THUMB_IMG, /w-auto/)
  assert.match(THUMB_IMG, /min-w-\[calc\(var\(--th\)\*0\.75\)\]/)
  assert.match(THUMB_IMG, /max-w-\[calc\(var\(--th\)\*1\.7778\)\]/)
})
