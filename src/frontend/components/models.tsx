export type ComponentData = {
  _id: string,
  type: string,
  material: string,
  complexity: number,
  fragment: boolean,
  assembly: boolean,
  color: Array<number>,
  geometry: {
    extrusion: {
      height: number,
      profile: ComponentPolylinePoints,
    },
    mesh: {
      v: ComponentMeshVertices,
      f: ComponentMeshFaces,
      c: ComponentMeshColors
    }
  },
  validated: boolean,
  bbx: ComponentBoundingBox,
  iframe: {
    o: Array<number>,
    x: Array<number>,
    y: Array<number>,
    z: Array<number>
  }
  descriptors: {
    roundness: number
  },
  processes: {
  },
  attributes: {
  }
}

export type ComponentBoundingBox =  Array<Array<number>>
export type ComponentPolylinePoints = Array<Array<number>>
export type ComponentMeshVertices = Array<Array<number>>
export type ComponentMeshFaces = Array<Array<number>>
export type ComponentMeshColors = Array<Array<number>>