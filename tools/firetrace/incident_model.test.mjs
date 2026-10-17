import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {printedClockSeconds,resolveMoment,seekWhenReady,requestAnalysis,acceptLiveAnalysis,inferenceFailureNotice,reviewNotesFor} from './incident_model.mjs';
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
const reply=(status,body)=>async()=>new Response(body,{status});
const frameOf=id=>structuredClone(bundle.frames.find(f=>f.id===id));
test('a seek requested before metadata loads follows the last selected frame, not the first',()=>{
 const video={readyState:0,currentTime:0};
 seekWhenReady(video,32);seekWhenReady(video,77);
 video.onloadedmetadata();
 assert.equal(video.currentTime,77);
 const ready={readyState:1,currentTime:0};seekWhenReady(ready,3);assert.equal(ready.currentTime,3);
});
test('every moment seeks inside its camera clip',()=>{
 for(let i=0;i<3;i++)for(const f of resolveMoment(bundle,i).frames){const c=bundle.cameras.find(x=>x.id===f.cameraId);assert.ok(f.sourceVideoSecond-c.sourceClipStart>=0);}
});
test('failed inference never exposes raw errors and keeps the saved response',async()=>{
 for(const [fetchFn,expected] of [
  [reply(502,'{}'),/HTTP 502/],
  [reply(502,'<html>Bad Gateway</html>'),/HTTP 502/],
  [async()=>{throw new TypeError('Failed to fetch');},/No se pudo contactar/],
  [reply(502,JSON.stringify({error:'El servicio no pudo completar el análisis'})),/análisis\. Se conserva/],
  [reply(200,JSON.stringify({content:'x',imageSha256:'00'})),/no corresponde/],
 ]){
  const frame={...frameOf('delilah-110'),analysis:{content:'guardada',imageSha256:'9a2aab2c33b261b1ba7df39e310af1e110bf8b5e871aa01eaf73bfd6b722bbc6'}};
  let notice;try{await requestAnalysis(frame,'data:',fetchFn);assert.fail('should reject');}catch(e){notice=inferenceFailureNotice(e,frame);}
  assert.match(notice,expected);assert.doesNotMatch(notice,/undefined|Unexpected token|Failed to fetch|JSON/);
  assert.equal(frame.analysis.content,'guardada');assert.equal(frame.presentationMode,undefined);
 }
});
test('a live response keeps the original model text and drops the review note meant for it',async()=>{
 const frame=frameOf('delilah-110');frame.analysis={content:'texto original',imageSha256:frame.imageSha256};
 assert.match(reviewNotesFor(frame),/cámara fija de torre/);
 await requestAnalysis(frame,'data:',reply(200,JSON.stringify({content:'nuevo',model:'m',imageSha256:frame.imageSha256})));
 acceptLiveAnalysis(frame,{content:'otro',imageSha256:frame.imageSha256});
 assert.equal(frame.analysis.content,'otro');assert.equal(frame.savedAnalysis.content,'texto original');
 assert.doesNotMatch(reviewNotesFor(frame),/cámara fija de torre/);assert.match(reviewNotesFor(frame),/no está revisada/);
 assert.equal(reviewNotesFor(frameOf('delilah-86')),'');
});
