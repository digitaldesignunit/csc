// Auto-generated from backend OpenAPI schema
// Generated on: 2026-10-02T21:09:58.863Z
// Source: http://127.0.0.1:8011/schema/catalog-shared

export interface Bounds {
  min: number[];
  max: number[];
}

export interface DeviationMapFace {
  file: string;
  width: number;
  height: number;
  distance: MapScale;
}

export interface DeviationMaps {
  resolution_mm: number;
  channels: string[];
  faces: Record<string, unknown>;
}

export interface Fit {
  method: 'authored' | 'obb' | 'ransac' | 'lsq' | 'hull';
  source?: FitSource | null;
  n_points?: number | null;
  inlier_ratio?: number | null;
  rms_mm?: number | null;
  max_mm?: number | null;
  p95_mm?: number | null;
  spec_version?: number | null;
  computed_at?: string | null;
}

export interface FitSource {
  kind: 'meshes' | 'point_clouds';
  index: number;
  resolution: 'original' | 'reduced' | 'preview';
}

export interface Frame {
  o: number[];
  x: number[];
  y: number[];
  z: number[];
}

export interface GeoLocation {
  lat: number;
  lon: number;
}

export interface Geometry {
  meshes?: Mesh[];
  point_clouds?: PointCloud[];
  proxies?: Proxy[];
}

export interface MapScale {
  scale_mm: number;
  offset_mm: number;
}

export interface Mesh {
  vertices: number[][];
  faces: number[][];
  colors?: number[][] | null;
}

export interface PointCloud {
  points: number[][];
  colors?: number[][] | null;
}

export interface Proxy {
  primitive: 'box' | 'prism' | 'cylinder' | 'hull';
  role: 'primary' | 'part';
  params: Record<string, unknown>;
  placement: Frame;
  fit: Fit;
  deviation_maps?: DeviationMaps | null;
  regions?: Region[];
}

export interface Region {
  label: string;
  bounds: Bounds;
  resolution_hint: 'original' | 'reduced' | 'proxy';
  reason: 'connection' | 'damage' | 'feature' | 'other';
  source: 'derived' | 'assigned';
}

// Shared catalog value types (frame, location, geometry, proxies)
export type ComponentComplexity = 0 | 1 | 2 | 3;
