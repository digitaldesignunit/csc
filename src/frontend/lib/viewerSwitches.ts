/**
 * The detail switches of the viewer have an "Off" choice (0.6.3.0, decision
 * 8.165 C): Proxy / Preview / Reduced / Original / Off for the mesh and
 * Preview / Original / Off for the point cloud. Off is a display state only:
 * it hides the layer and loads nothing, and the level that was chosen stays,
 * so choosing a level again shows the layer at that level.
 *
 * Run: npm test
 */

export const SWITCH_OFF = 'off'

export type SwitchOption = { value: string; label: string }

export const OFF_OPTION: SwitchOption = { value: SWITCH_OFF, label: 'Off' }

/** A switch: the level chosen last, and whether the layer is hidden. */
export type SwitchState<L extends string> = { level: L; off: boolean }

/** What the switch shows as chosen. */
export function switchValue<L extends string>(state: SwitchState<L>): L | typeof SWITCH_OFF {
  return state.off ? SWITCH_OFF : state.level
}

/** The state after the user picks `value`: Off keeps the level, a level ends Off. */
export function chooseSwitch<L extends string>(state: SwitchState<L>, value: string): SwitchState<L> {
  if (value === SWITCH_OFF) return { level: state.level, off: true }
  return { level: value as L, off: false }
}

/** The levels of a switch and Off as the last choice. */
export function withOff(options: readonly SwitchOption[]): SwitchOption[] {
  return [...options, OFF_OPTION]
}

/** The visibility flags of the single objects, all hidden while the layer is Off. */
export function shownFlags(flags: readonly boolean[], off: boolean): boolean[] {
  return off ? flags.map(() => false) : [...flags]
}

/** "Show edges" belongs to the mesh (or the proxy): it has no effect while that is Off. */
export function edgesControl(showEdges: boolean, meshOff: boolean): { checked: boolean; disabled: boolean } {
  return { checked: showEdges, disabled: meshOff }
}

/** A piece with a mesh starts with its point cloud hidden (as before the switch had Off). */
export function pointCloudStartsOff(meshCount: number): boolean {
  return meshCount > 0
}

/** The mesh switch is for a piece that has a mesh or a proxy to show. */
export function hasMeshSwitch(meshCount: number, hasProxy: boolean): boolean {
  return meshCount > 0 || hasProxy
}
