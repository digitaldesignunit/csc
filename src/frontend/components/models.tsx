export type ComponentData = {
  _id: string;
  type: string;
  material: string;
  materialthickness: number;
  color: Array<number>;
  geometry: {
    polyline: ComponentPolylinePoints;
  };
}

export type ComponentPolylinePoints = Array<Array<number>>;