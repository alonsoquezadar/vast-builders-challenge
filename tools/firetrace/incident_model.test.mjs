import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {printedClockSeconds,resolveMoment} from './incident_model.mjs';
const bundle=JSON.parse(readFileSync(new URL('./evidence/garnet/manifest.json',import.meta.url)));
test('paired observations preserve their exact printed clock difference, without claiming synchronization',()=>{
 const pair=resolveMoment(bundle,0);
 assert.equal(pair.frames[0].id,'delilah-86');
 assert.equal(pair.frames[1].id,'buckrock-222');
 assert.ok(Math.abs(pair.printedOffsetSeconds-583.72)<.001);
 assert.equal(pair.synchronized,false);
});
test('all three moments resolve one real frame for each camera',()=>{
 for(let i=0;i<3;i++){const pair=resolveMoment(bundle,i);assert.equal(new Set(pair.frames.map(f=>f.cameraId)).size,2);assert.ok(pair.printedOffsetSeconds>0);}
});
test('invalid clocks, unknown moments, duplicate cameras and different dates are rejected',()=>{
 for(const t of ['2025-08-27T25:00:00','2025-08-27T12:60:00','2025-08-27T12:00:00Z','not a time'])assert.throws(()=>printedClockSeconds(t));
 assert.throws(()=>resolveMoment(bundle,99));
 const duplicate=structuredClone(bundle);duplicate.moments[0].frameIds=['delilah-86','delilah-110'];assert.throws(()=>resolveMoment(duplicate,0));
 const dates=structuredClone(bundle);dates.frames.find(f=>f.id==='buckrock-222').printedTime='2025-08-28T16:26:41.25';assert.throws(()=>resolveMoment(dates,0));
});
