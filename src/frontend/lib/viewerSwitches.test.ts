/**
 * The Off choice of the viewer's detail switches (decision 8.165 C): Off
 * hides, loads nothing, and the level chosen before comes back with it.
 *
 * Run: npm test
 */
import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  OFF_OPTION,
  chooseSwitch,
  edgesControl,
  hasMeshSwitch,
  pointCloudStartsOff,
  shownFlags,
  switchValue,
  withOff,
  type SwitchState,
} from '@/lib/viewerSwitches'

type MeshLevel = 'proxy' | 'preview' | 'reduced' | 'original'

const preview: SwitchState<MeshLevel> = { level: 'preview', off: false }

test('a switch that was never touched shows its level', () => {
  assert.equal(switchValue(preview), 'preview')
})

test('Off is the last choice of the mesh switch and of the point cloud switch', () => {
  const mesh = withOff([
    { value: 'proxy', label: 'Proxy' },
    { value: 'preview', label: 'Preview' },
    { value: 'reduced', label: 'Reduced' },
    { value: 'original', label: 'Original' },
  ])
  assert.deepEqual(mesh.map((o) => o.label), ['Proxy', 'Preview', 'Reduced', 'Original', 'Off'])
  const cloud = withOff([
    { value: 'preview', label: 'Preview' },
    { value: 'original', label: 'Original' },
  ])
  assert.deepEqual(cloud.map((o) => o.label), ['Preview', 'Original', 'Off'])
  assert.deepEqual(cloud[cloud.length - 1], OFF_OPTION)
})

test('Off hides and keeps the level', () => {
  const off = chooseSwitch({ level: 'reduced', off: false } as SwitchState<MeshLevel>, 'off')
  assert.deepEqual(off, { level: 'reduced', off: true })
  assert.equal(switchValue(off), 'off')
})

test('a level chosen after Off shows the layer at that level', () => {
  const was: SwitchState<MeshLevel> = { level: 'original', off: false }
  const off = chooseSwitch(was, 'off')
  assert.deepEqual(chooseSwitch(off, 'original'), was)
  assert.deepEqual(chooseSwitch(off, 'preview'), { level: 'preview', off: false })
})

test('choosing Off twice changes nothing more', () => {
  const off = chooseSwitch(chooseSwitch(preview, 'off'), 'off')
  assert.deepEqual(off, { level: 'preview', off: true })
})

test('choosing a level while shown only changes the level', () => {
  assert.deepEqual(chooseSwitch(preview, 'reduced'), { level: 'reduced', off: false })
})

test('the state is not changed in place', () => {
  const state: SwitchState<MeshLevel> = { level: 'preview', off: false }
  chooseSwitch(state, 'off')
  assert.deepEqual(state, { level: 'preview', off: false })
})

test('Off hides every single mesh or cloud, a shown layer keeps its flags', () => {
  assert.deepEqual(shownFlags([true, false, true], true), [false, false, false])
  assert.deepEqual(shownFlags([true, false, true], false), [true, false, true])
  assert.deepEqual(shownFlags([], true), [])
})

test('shown flags are a copy', () => {
  const flags = [true, false]
  const shown = shownFlags(flags, false)
  shown[0] = false
  assert.deepEqual(flags, [true, false])
})

test('Show edges keeps its value and is disabled while the mesh is Off', () => {
  assert.deepEqual(edgesControl(true, false), { checked: true, disabled: false })
  assert.deepEqual(edgesControl(true, true), { checked: true, disabled: true })
  assert.deepEqual(edgesControl(false, true), { checked: false, disabled: true })
})

test('only a piece with a mesh starts with its point cloud hidden', () => {
  assert.equal(pointCloudStartsOff(0), false)
  assert.equal(pointCloudStartsOff(1), true)
  assert.equal(pointCloudStartsOff(3), true)
})

test('the mesh switch is for a mesh or a proxy', () => {
  assert.equal(hasMeshSwitch(2, false), true)
  assert.equal(hasMeshSwitch(0, true), true)
  assert.equal(hasMeshSwitch(0, false), false)
})
