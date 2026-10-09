import assert from 'node:assert/strict'
import { test } from 'node:test'

import { OTHER_COLOR, PALETTE, colorKey, colorMap, keyLabel, legendOf } from './mapColors'

type Over = { dataset?: string | null; material?: string | null; shape_class?: string | null; in_place?: boolean }
const P = (id: string, over: Over = {}) => ({ id, ...over })

test('the key of a point depends on the colouring', () => {
  const point = { dataset: 'a', material: 'concrete', shape_class: 'linear', in_place: true }
  assert.equal(colorKey(point, 'dataset'), 'a')
  assert.equal(colorKey(point, 'material'), 'concrete')
  assert.equal(colorKey(point, 'shape_class'), 'linear')
  assert.equal(colorKey(point, 'circulation'), 'in_place')
  assert.equal(colorKey({}, 'circulation'), 'not_in_place')
  assert.equal(colorKey({}, 'dataset'), '')
})

test('labels: shape class and circulation by words, material by its label', () => {
  assert.equal(keyLabel('shape_class', 'linear'), 'Linear')
  assert.equal(keyLabel('circulation', 'in_place'), 'In place')
  assert.equal(keyLabel('circulation', 'not_in_place'), 'Not in place')
  assert.equal(keyLabel('material', 'concrete', { material: () => 'Concrete' }), 'Concrete')
  assert.equal(keyLabel('dataset', ''), 'Not stated')
})

test('the legend lists the most frequent value first with its count', () => {
  const points = [
    P('1', { dataset: 'b' }), P('2', { dataset: 'a' }), P('3', { dataset: 'a' }), P('4', { dataset: 'a' }), P('5', {}),
  ]
  const legend = legendOf(points, 'dataset')
  assert.deepEqual(legend.map((e) => [e.key, e.count]), [['a', 3], ['b', 1], ['', 1]])
  assert.equal(legend[0].color, PALETTE[0])
  assert.equal(legend[1].color, PALETTE[1])
  assert.equal(legend[2].color, OTHER_COLOR)
  assert.equal(legend[2].label, 'Not stated')
})

test('after ten values the rest share one colour', () => {
  const points = Array.from({ length: 13 }, (_, i) => P(String(i), { dataset: `d${String(i).padStart(2, '0')}` }))
  const legend = legendOf(points, 'dataset')
  assert.equal(legend.length, 11)
  assert.deepEqual(legend[10], { key: '__other__', label: 'Other', color: OTHER_COLOR, count: 3 })
  const colors = colorMap(points, 'dataset')
  assert.equal(colors.get('0'), PALETTE[0])
  assert.equal(colors.get('12'), OTHER_COLOR)
})

test('circulation has two fixed colours and only what is there', () => {
  const both = legendOf([P('1', { in_place: true }), P('2', {})], 'circulation')
  assert.deepEqual(both.map((e) => e.key), ['in_place', 'not_in_place'])
  assert.notEqual(both[0].color, both[1].color)
  assert.deepEqual(legendOf([P('1', {})], 'circulation').map((e) => e.key), ['not_in_place'])
})

test('the colour of a point follows its value', () => {
  const colors = colorMap([P('1', { dataset: 'a' }), P('2', { dataset: 'b' }), P('3', { dataset: 'a' })], 'dataset')
  assert.equal(colors.get('1'), colors.get('3'))
  assert.notEqual(colors.get('1'), colors.get('2'))
})
