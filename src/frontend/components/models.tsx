export type ComponentData = {
  _id: string,
  type: string,
  material: string,
  materialthickness: number,
  complexity: number,
  fragment: boolean,
  assembly: boolean,
  color: Array<number>,
  geometry: {
    polyline: ComponentPolylinePoints,
    mesh: {
      v: ComponentMeshVertices,
      f: ComponentMeshFaces
    }
  },
  validated: boolean,
  bbx: {
    xy: ComponentPolylinePoints,
    xyz: ComponentPolylinePoints
  },
  iframe: {
    o: Array<number>,
    x: Array<number>,
    y: Array<number>,
    z: Array<number>
  }
  descriptors: {
    roundness: number
  },
  indicators: {
    eco2e: number
  }
}

export type ComponentBoundingBox = {
  xy: ComponentPolylinePoints,
  xyz: ComponentPolylinePoints
}
export type ComponentPolylinePoints = Array<Array<number>>
export type ComponentMeshVertices = Array<Array<number>>
export type ComponentMeshFaces = Array<Array<number>>