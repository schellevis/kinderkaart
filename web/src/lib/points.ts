/**
 * Decodes the points.json payload into typed Point objects.
 * The payload shape matches data_pipeline/build_points.py:
 *   { fields: string[], categories: string[], points: (string|number|boolean|null)[][] }
 *
 * Field order: poi_id, lat, lon, cats, name, indoor, free, age_min, age_max
 * cats is a bitmask over the sorted categories array.
 */

export interface Point {
  poiId: string;
  lat: number;
  lon: number;
  cats: string[];
  name: string;
  indoor: boolean | null;
  free: boolean | null;
  ageMin: number | null;
  ageMax: number | null;
}

export interface PointsPayload {
  fields: string[];
  categories: string[];
  points: (string | number | boolean | null)[][];
}

export function decodePoints(payload: PointsPayload): Point[] {
  const { fields, categories, points } = payload;

  const fi = (name: string) => fields.indexOf(name);
  const iPoiId = fi("poi_id");
  const iLat = fi("lat");
  const iLon = fi("lon");
  const iCats = fi("cats");
  const iName = fi("name");
  const iIndoor = fi("indoor");
  const iFree = fi("free");
  const iAgeMin = fi("age_min");
  const iAgeMax = fi("age_max");

  return points.map((row) => {
    const mask = row[iCats] as number;
    const cats: string[] = [];
    for (let bit = 0; bit < categories.length; bit++) {
      if (mask & (1 << bit)) {
        cats.push(categories[bit]);
      }
    }
    return {
      poiId: row[iPoiId] as string,
      lat: row[iLat] as number,
      lon: row[iLon] as number,
      cats,
      name: row[iName] as string,
      indoor: row[iIndoor] == null ? null : (row[iIndoor] as boolean),
      free: row[iFree] == null ? null : (row[iFree] as boolean),
      ageMin: row[iAgeMin] == null ? null : (row[iAgeMin] as number),
      ageMax: row[iAgeMax] == null ? null : (row[iAgeMax] as number),
    };
  });
}
