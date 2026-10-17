import {test} from 'node:test';
import assert from 'node:assert/strict';
import {distance,destination,pointsAt,validateObservationCollection} from './geo.mjs';

test('a camera bearing produces a geodesic sightline of the requested length',()=>{
 const origin=[-121.9,41.4];
 const east=destination(origin,90,12000);
 assert.ok(east[0]>origin[0]);
 assert.ok(Math.abs(distance(origin,east)-12000)<0.01);
 const north=destination(origin,0,12000);
 assert.ok(north[1]>origin[1]);
 assert.ok(Math.abs(north[0]-origin[0])<1e-9);
});
test('timeline excludes future observations and expired observations',()=>{
 const feature=t=>({properties:{observedAt:t}});
 const now=Date.parse('2026-10-17T12:00:00Z');
 const items=[feature('2026-10-16T11:59:59Z'),feature('2026-10-16T12:00:00Z'),feature('2026-10-17T12:00:00Z'),feature('2026-10-17T12:00:01Z')];
 assert.deepEqual(pointsAt(items,now),items.slice(1,3));
});
test('geographic observations require explicit timezones and valid geometry',()=>{
 const data={type:'FeatureCollection',features:[{type:'Feature',geometry:{type:'Point',coordinates:[-122,41]},properties:{observedAt:'2026-10-17T12:00:00Z'}}]};
 assert.equal(validateObservationCollection(data).features.length,1);
 const badTime=structuredClone(data);badTime.features[0].properties.observedAt='2026-10-17T12:00:00';
 assert.throws(()=>validateObservationCollection(badTime),/time zone/);
 const badPoint=structuredClone(data);badPoint.features[0].geometry.coordinates=[-222,41];
 assert.throws(()=>validateObservationCollection(badPoint),/Invalid geographic coordinates/);
 const badRing=structuredClone(data);badRing.features[0].geometry={type:'Polygon',coordinates:[[[-122,41],[-121,41],[-121,42],[-122,42]]]};
 assert.throws(()=>validateObservationCollection(badRing),/must be closed/);
});
