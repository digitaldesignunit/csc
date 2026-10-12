import assert from 'node:assert/strict'
import test from 'node:test'

import { HKS_T_MAX, HKS_T_MIN, HKS_TIMES, chartPoints, hksTimes, linePath, parseHks } from '@/lib/hks'

const values = (fn: (i: number) => number) => Array.from({ length: 2 * HKS_TIMES }, (_, i) => fn(i))

test('the time grid is log-spaced between the frozen ends', () => {
  const times = hksTimes()
  assert.equal(times.length, HKS_TIMES)
  assert.ok(Math.abs(times[0] - HKS_T_MIN) < 1e-12)
  assert.ok(Math.abs(times[HKS_TIMES - 1] - HKS_T_MAX) < 1e-9)
  const ratio = times[1] / times[0]
  for (let i = 2; i < times.length; i += 1) assert.ok(Math.abs(times[i] / times[i - 1] - ratio) < 1e-9)
})

test('a stored HKS splits into its mean and variance curves', () => {
  const curves = parseHks({ hks: values((i) => i) })
  assert.ok(curves)
  assert.equal(curves.mean.length, HKS_TIMES)
  assert.equal(curves.mean[0], 0)
  assert.equal(curves.variance[0], HKS_TIMES)
})

test('no descriptor, a wrong length or a bad value gives no curves', () => {
  assert.equal(parseHks(null), null)
  assert.equal(parseHks({}), null)
  assert.equal(parseHks({ hks: [1, 2, 3] }), null)
  assert.equal(parseHks({ hks: values((i) => (i === 3 ? Number.NaN : i)) }), null)
  assert.equal(parseHks({ hks: values((i) => (i === 3 ? 'x' as unknown as number : i)) }), null)
})

test('the chart runs from the smallest to the largest value, top is large', () => {
  const { points, min, max } = chartPoints([1, 3, 2], 100, 50, 5)
  assert.equal(min, 1)
  assert.equal(max, 3)
  assert.equal(points[0].x, 5)
  assert.equal(points[2].x, 95)
  assert.equal(points[0].y, 45)
  assert.equal(points[1].y, 5)
  assert.ok(points[2].y < points[0].y && points[2].y > points[1].y)
})

test('a flat curve sits in the middle', () => {
  const { points } = chartPoints([2, 2, 2], 100, 50)
  assert.ok(points.every((p) => p.y === 25))
})

test('the path starts with a move and joins the rest', () => {
  assert.equal(linePath([{ x: 1, y: 2 }, { x: 3, y: 4 }]), 'M 1.0 2.0 L 3.0 4.0')
})
