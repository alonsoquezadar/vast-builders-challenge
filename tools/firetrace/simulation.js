const $=id=>document.getElementById(id);
const CALFIRE=[-121.41472,35.90356];
const SAVED=[-119.027914,36.86508];
const LABEL='ILLUSTRATIVE SIMULATION · OPERATOR ASSUMPTIONS';
const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const count=n=>Math.round(n).toLocaleString('en-GB');
const stamp=value=>{const t=Date.parse(value);if(!Number.isFinite(t))return String(value);const iso=new Date(t).toISOString();return `${Number(iso.slice(8,10))} ${MONTHS[Number(iso.slice(5,7))-1]} ${iso.slice(0,4)} ${iso.slice(11,16)} UTC`;};
const fields={windFromDeg:['windFrom',0,360],windSpeedMps:['windSpeed',0,30],baseSpreadMMin:['base',0.1,30],fuelFactor:['fuel',0.1,2],durationMin:['duration',1,60]};
let seed=null,seedKind=null,dem=null,result=null,pick=false,marker=null,ticket=0,timer=null,weather=null;
const map=new maplibregl.Map({container:'map',center:[-120.2,36.4],zoom:6,pitch:0,style:{version:8,sources:{satellite:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],tileSize:256,attribution:'Imagery © Esri & contributors'},dem:{type:'raster-dem',tiles:['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'],encoding:'terrarium',tileSize:256,maxzoom:15,attribution:'Elevation: AWS Terrain Tiles'}},layers:[{id:'satellite',type:'raster',source:'satellite'}]}});
map.addControl(new maplibregl.NavigationControl());map.addControl(new maplibregl.ScaleControl());
let ready=false;
map.on('load',()=>{ready=true;map.setTerrain({source:'dem',exaggeration:1});map.addSource('scenario',{type:'geojson',data:{type:'FeatureCollection',features:[]}});
 map.addLayer({id:'scenario-fill',type:'fill',source:'scenario',paint:{'fill-color':'#e08a3c','fill-opacity':0.6}});});
function say(id,text){$(id).textContent=text;}
function readParams(){const out={};for(const [key,[id,lo,hi]] of Object.entries(fields)){const raw=$(id).value.trim();const v=Number(raw);if(raw===''||!Number.isFinite(v)||v<lo||v>hi)throw new Error(`${$(id).parentElement.firstChild.textContent.trim()}: value between ${lo} and ${hi}.`);out[key]=v;}return out;}
function clearResult(note){result=null;ticket++;stop();$('export').disabled=true;$('time').disabled=true;$('play').disabled=true;say('time-out','—');say('legend-end','—');if(ready)map.getSource('scenario').setData({type:'FeatureCollection',features:[]});if(note)say('status',note);}
function setSeed(lonLat,kind){const lon=Number(lonLat[0].toFixed(6)),lat=Number(lonLat[1].toFixed(6));seed=[lon,lat];seedKind=kind;dem=null;clearWeather();say('provenance','Terrain: not loaded for this seed.');
 if(marker)marker.remove();marker=new maplibregl.Marker({color:'#8e2f23'}).setLngLat(seed).setPopup(new maplibregl.Popup().setText('Hypothetical seed chosen by the operator. It is not a detected hotspot.')).addTo(map);
 const kinds={map:'chosen on the map',calfire:'reference published by CAL FIRE (Plaskett Fire), used only as an assumption',saved:'point with locally saved terrain, used only as an assumption'};
 say('seed-status',`HYPOTHETICAL seed ${kinds[kind]}: ${lon}, ${lat}.`);clearResult('Seed changed. Load the terrain and run again.');
 map.flyTo({center:seed,zoom:13.5,pitch:55,bearing:-20});}
function setPick(on){pick=on;$('pick').setAttribute('aria-pressed',String(on));map.getCanvas().style.cursor=on?'crosshair':'';}
$('pick').onclick=()=>setPick(!pick);
map.on('click',e=>{if(!pick)return;setPick(false);setSeed([e.lngLat.lng,e.lngLat.lat],'map');});
$('calfire').onclick=()=>setSeed(CALFIRE,'calfire');
$('saved').onclick=()=>setSeed(SAVED,'saved');
for(const [id] of Object.values(fields))$(id).addEventListener('input',()=>{if(id==='windFrom'||id==='windSpeed')clearWeather();clearResult('Assumptions changed. Press ‘Run scenario’.');syncDuration();});
function syncDuration(){const d=Number($('duration').value);if(Number.isFinite(d)&&d>=1&&d<=60)$('time').max=String(d);}
async function getJson(url,options){const response=await fetch(url,options);let body;try{body=await response.json();}catch{throw new Error(`Invalid response (${response.status}).`);}if(!response.ok)throw new Error(body.error||body.message||`Error ${response.status}.`);return body;}
async function loadDem(){if(!seed)throw new Error('Choose a seed first.');const mine=ticket;say('status','Loading real terrain…');
 const body=await getJson(`/api/scenario-terrain?lon=${seed[0]}&lat=${seed[1]}`);if(mine!==ticket)throw new Error('Outdated operation.');
 const flat=(body.elevations||[]).flat();if(body.terrainStatus!=='real-dem'||!flat.length||!flat.every(Number.isFinite))throw new Error('The terrain received is not a complete real DEM; it will not be simulated.');
 dem=body;const lo=Math.min(...flat),hi=Math.max(...flat);
 say('provenance',`Terrain: ${body.terrainSource} · status ${body.terrainStatus}${body.terrainMode?' · '+body.terrainMode:''}\nQueried: ${body.terrainFetchedAt?stamp(body.terrainFetchedAt):'no date'} (not the acquisition date)\nGrid ${body.elevations.length}×${body.elevations.length}, ${body.cellSizeM} m cells · altitude ${count(lo)}–${count(hi)} m\nSeed: ${seed.join(', ')} (hypothetical)`);
 say('status','Terrain loaded. Review the assumptions and run.');}
$('dem').onclick=()=>loadDem().catch(e=>say('status',e.message));
function colors(max){return ['interpolate',['linear'],['get','arrivalMin'],0,'#f3d27a',max/2,'#e08a3c',max,'#8e2f23'];}
$('run').onclick=async()=>{try{if(!ready)throw new Error('Wait for the map to finish loading.');const params=readParams();if(!seed)throw new Error('Choose a seed first.');if(!dem)await loadDem();const mine=++ticket;say('status','Calculating illustrative scenario…');
 const body=await getJson('/api/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({origin:seed,...params,...(weather?{weatherTimeUtc:weather.timeUtc}:{})})});if(mine!==ticket)return;
 if(body.type!=='FeatureCollection'||body.properties?.validated!==false||body.properties?.mode!=='illustrative-scenario')throw new Error('Unexpected response from the server; it is not displayed.');
 result={body,params,seed:seed.slice(),seedKind,demMeta:{terrainSource:dem.terrainSource,terrainStatus:dem.terrainStatus,terrainFetchedAt:dem.terrainFetchedAt,terrainMode:dem.terrainMode,cellSizeM:dem.cellSizeM}};
 map.getSource('scenario').setData(body);map.setPaintProperty('scenario-fill','fill-color',colors(params.durationMin));
 const t=$('time');t.max=String(params.durationMin);t.value=String(params.durationMin);t.disabled=false;$('play').disabled=false;$('export').disabled=false;apply();say('legend-end',`${params.durationMin} min`);
 say('status',`Scenario calculated: ${count(body.features.length)} cells up to minute ${params.durationMin}. Illustrative, unvalidated.${body.properties.boundaryReached?' The edge of the DEM is reached: the calculation ends there because of the grid limit, not because of containment.':''}`);}catch(e){say('status',e.message);}};
function apply(){const t=Number($('time').value);if(ready)map.setFilter('scenario-fill',['<=',['get','arrivalMin'],t]);const n=result?result.body.features.filter(f=>f.properties.arrivalMin<=t).length:0;say('time-out',`minute ${t.toFixed(1)} · ${count(n)} cells`);}
$('time').addEventListener('input',()=>{stop();apply();});
function stop(){if(timer)cancelAnimationFrame(timer);timer=null;$('play').setAttribute('aria-pressed','false');$('play').textContent='Play';}
$('play').onclick=()=>{if(timer){stop();return;}const t=$('time'),max=Number(t.max);if(Number(t.value)>=max)t.value='0';$('play').setAttribute('aria-pressed','true');$('play').textContent='Pause';let last=performance.now();
 const step=now=>{const v=Number(t.value)+(now-last)/1000*(max/12);last=now;t.value=String(Math.min(max,v));apply();if(v>=max){stop();return;}timer=requestAnimationFrame(step);};timer=requestAnimationFrame(step);};
$('export').onclick=()=>{if(!result)return;const {body,params,seed:s,seedKind:k,demMeta}=result;
 const out={...body,properties:{...body.properties,export:{exportedAt:new Date().toISOString(),label:LABEL,seed:s,seedKind:k,operatorAssumptions:{...params,windSource:body.properties.meteorology.dataClass},demProvenance:demMeta,note:'Illustrative scenario. Fuel and seed are hypothetical; the wind provenance is recorded in meteorology.'}}};
 const url=URL.createObjectURL(new Blob([JSON.stringify(out)],{type:'application/geo+json'}));const a=document.createElement('a');a.href=url;a.download='firetrace-illustrative-scenario.geojson';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
clearResult();syncDuration();say('status','Choose a seed to begin.');

function clearWeather(){weather=null;say('weather-status','No historical selection. The wind is a manual assumption.');}
$('weather-time').addEventListener('input',()=>{clearWeather();clearResult('Date changed. Load the historical wind again.');});
$('weather-load').onclick=async()=>{try{
 if(!seed)throw new Error('Choose the Garnet seed first.');
 const stamp=$('weather-time').value;if(!stamp)throw new Error('Choose a date and time (UTC).');
 clearResult('Selecting historical wind…');clearWeather();const mine=ticket;say('weather-status','Loading historical weather model…');
 const row=await getJson('/api/scenario-weather?time='+encodeURIComponent(new Date(stamp+'Z').toISOString()));
 if(mine!==ticket)return;
 const distance=Math.hypot((seed[0]-row.point.lon)*Math.cos(seed[1]*Math.PI/180),seed[1]-row.point.lat)*111195;
 if(distance>50000)throw new Error('The Garnet weather point is more than 50 km from the seed. Choose a nearby seed.');
 $('windFrom').value=row.windFromDeg;$('windSpeed').value=row.windSpeedMps;
 clearResult('Historical wind selected. Run the scenario again.');weather=row;
 say('weather-status',`${stamp(row.timeUtc)} · from ${row.windFromDeg}° · ${row.windSpeedMps} m/s · RH ${row.rhPct}% (context only). ${row.source}. Point: ${row.point.lat}, ${row.point.lon}.`);
 }catch(e){clearWeather();say('weather-status',e.message);}};
