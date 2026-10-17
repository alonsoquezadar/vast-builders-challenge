export function distance(a, b) {
  const rad = Math.PI / 180;
  const dLat = (b[1] - a[1]) * rad, dLon = (b[0] - a[0]) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - Math.min(1, h)));
}

export function destination(origin, bearing, meters) {
  const r = Math.PI / 180, d = meters / 6371000, lat = origin[1] * r, lon = origin[0] * r, angle = bearing * r;
  const lat2 = Math.asin(Math.sin(lat) * Math.cos(d) + Math.cos(lat) * Math.sin(d) * Math.cos(angle));
  const lon2 = lon + Math.atan2(Math.sin(angle) * Math.sin(d) * Math.cos(lat), Math.cos(d) - Math.sin(lat) * Math.sin(lat2));
  return [lon2 / r, lat2 / r];
}

export function validateObservationCollection(data) {
  if (data?.type !== 'FeatureCollection' || !Array.isArray(data.features) || data.features.length > 10000) throw new Error('A GeoJSON FeatureCollection of up to 10,000 features is required.');
  function coordinates(value) {
    if (!Array.isArray(value) || !value.length) throw new Error('Empty coordinates.');
    if (typeof value[0] === 'number') {
      if (value.length < 2 || !value.slice(0, 2).every(Number.isFinite) || Math.abs(value[0]) > 180 || Math.abs(value[1]) > 90) throw new Error('Invalid geographic coordinates.');
    } else value.forEach(coordinates);
  }
  return { type: 'FeatureCollection', features: data.features.map((f, i) => {
    if (f?.type !== 'Feature' || !['Point', 'Polygon', 'MultiPolygon', 'LineString'].includes(f.geometry?.type)) throw new Error(`Unsupported geometry in feature ${i + 1}.`);
    coordinates(f.geometry.coordinates);
    const observedAt = f.properties?.observedAt;
    if (typeof observedAt !== 'string' || !Number.isFinite(Date.parse(observedAt)) || !/(Z|[+-]\d\d:\d\d)$/.test(observedAt)) throw new Error(`Feature ${i + 1} needs observedAt in ISO 8601 with a time zone.`);
    if (['Polygon', 'MultiPolygon'].includes(f.geometry.type)) {
      const polygons = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
      for (const polygon of polygons) for (const ring of polygon) if (ring.length < 4 || ring[0][0] !== ring.at(-1)[0] || ring[0][1] !== ring.at(-1)[1]) throw new Error('Polygon rings must be closed.');
    }
    return { type: 'Feature', geometry: f.geometry, properties: { observedAt, source: String(f.properties?.source || 'Operator import').slice(0, 120), status: 'operator-supplied' } };
  }) };
}

export function pointsAt(features, timestamp, windowMs = 86400000) {
  return features.filter(f => { const age = timestamp - Date.parse(f.properties.observedAt); return age >= 0 && age <= windowMs; });
}
