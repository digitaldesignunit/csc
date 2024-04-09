export type ComponentData = {
  _id: string
  type: string
  material: string
  materialthickness: number
  color: Array<number>
  geometry: {
    polyline: ComponentPolylinePoints
  }
  validated: boolean,
  bbx: {
    xy: ComponentPolylinePoints,
    xyz: ComponentPolylinePoints | null
  }
}

export type ComponentPolylinePoints = Array<Array<number>>;