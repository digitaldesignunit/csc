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
  location: ComponentLocation,
  iframe: {
    o: Array<number>,
    x: Array<number>,
    y: Array<number>,
    z: Array<number>
  }
  descriptors: {
    roundness: number
  },
  processes: object,
  attributes: object
}

export type ComponentBoundingBox = Array<number>  // [X, Y, Z] - maximum extents/dimensions of the component
export type ComponentPolylinePoints = Array<Array<number>>
export type ComponentMeshVertices = Array<Array<number>>
export type ComponentMeshFaces = Array<Array<number>>
export type ComponentMeshColors = Array<Array<number>>
export type ComponentLocation = {
  lat: number,
  lon: number
}

// Type guard function to safely check if bounding box data is valid
export function isValidBoundingBox(bbx: unknown): bbx is ComponentBoundingBox {
  return Array.isArray(bbx) && 
         bbx.length >= 3 && 
         bbx.every(val => typeof val === 'number' && !isNaN(val))
}