export type ComponentData = {
  _id: string
  type: string
  material: string
  materialthickness: number
  color: Array<number>
  geometry: {
    polyline: ComponentPolylinePoints
    mesh: {
      v: ComponentMeshVertices
      f: ComponentMeshFaces
    }
  }
  validated: boolean,
  bbx: {
    xy: ComponentPolylinePoints
    xyz: ComponentPolylinePoints
  }
}

export type ComponentPolylinePoints = Array<Array<number>>;
export type ComponentMeshVertices = Array<Array<number>>;
export type ComponentMeshFaces = Array<Array<number>>;