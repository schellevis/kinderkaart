import Supercluster from "supercluster";
import type { Point } from "./lib/points.js";

export interface ClusterFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    cluster: true;
    cluster_id: number;
    point_count: number;
    point_count_abbreviated: number | string;
  };
}

export interface PointFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: {
    cluster: false;
    poiId: string;
    name: string;
    cats: string[];
    /** Primary category (first element of cats) — used for map marker color. */
    cat0: string;
    indoor: boolean | null;
    free: boolean | null;
  };
}

export type AnyFeature = ClusterFeature | PointFeature;

interface PointProps {
  cluster: false;
  poiId: string;
  name: string;
  cats: string[];
  cat0: string;
  indoor: boolean | null;
  free: boolean | null;
}

function toGeoJSON(pt: Point): Supercluster.PointFeature<PointProps> {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: [pt.lon, pt.lat] },
    properties: {
      cluster: false as const,
      poiId: pt.poiId,
      name: pt.name,
      cats: pt.cats,
      cat0: pt.cats[0] ?? "",
      indoor: pt.indoor,
      free: pt.free,
    },
  };
}

export class Clusterer {
  private sc: Supercluster<PointProps>;
  private allPoints: Point[];
  private filteredPoints: Point[];

  constructor(points: Point[]) {
    this.allPoints = points;
    this.filteredPoints = points;
    this.sc = new Supercluster<PointProps>({ radius: 60, maxZoom: 16 });
    this.sc.load(points.map(toGeoJSON));
  }

  /** Rebuild the index from the subset matching filterFn. */
  update(filterFn: (pt: Point) => boolean): void {
    this.filteredPoints = this.allPoints.filter(filterFn);
    this.sc = new Supercluster<PointProps>({ radius: 60, maxZoom: 16 });
    this.sc.load(this.filteredPoints.map(toGeoJSON));
  }

  /** Number of points currently in the filtered index. */
  filteredCount(): number {
    return this.filteredPoints.length;
  }

  /** Returns clusters and points for the given bounding box and zoom. */
  getClusters(bbox: [number, number, number, number], zoom: number): AnyFeature[] {
    return this.sc.getClusters(bbox, zoom) as AnyFeature[];
  }

  /** Returns the leaves (individual points) of a cluster. */
  getLeaves(clusterId: number, limit?: number, offset?: number): AnyFeature[] {
    return this.sc.getLeaves(clusterId, limit, offset) as AnyFeature[];
  }
}

export function makeClusterer(points: Point[]): Clusterer {
  return new Clusterer(points);
}
