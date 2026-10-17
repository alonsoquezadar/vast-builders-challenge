import {createMapLayers,prepareWeather,nearestWeatherHour,weatherLines,evidenceWarnings,formatUtc,formatTimestamp,popupLines,mapLayerId} from './satellite-view.mjs';
const $=id=>document.getElementById(id), empty=()=>({type:'FeatureCollection',features:[]});
const positions={delilah:[-119.1175,36.80417],buckrock:[-118.86067,36.73727]};
const names={delilah:'Delilah Lookout 2',buckrock:'Buck Rock 1'};
const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const printed=v=>{const m=/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)/.exec(String(v??''));return m?`${Number(m[3])} ${MONTHS[Number(m[2])-1]} ${m[1]} ${m[4]}`:String(v??'');};
const state={fusion:null,layers:{},weather:[],summary:null,ready:false,layerControl:null,cursor:Date.parse('2025-08-27T19:49:00Z')/1000};
const map=new maplibregl.Map({container:'map',center:[-119.035,36.87],zoom:10.8,pitch:55,bearing:-20,style:{version:8,sources:{imagery:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],tileSize:256,attribution:'Imagery © Esri & contributors'},terrain:{type:'raster-dem',tiles:['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'],tileSize:256,encoding:'terrarium',maxzoom:15,attribution:'Elevation: AWS Terrain Tiles'}},layers:[{id:'imagery',type:'raster',source:'imagery'}]}});
map.addControl(new maplibregl.NavigationControl());map.addControl(new maplibregl.ScaleControl());
map.on('load',()=>{state.ready=true;map.setTerrain({source:'terrain',exaggeration:1});state.layerControl=createMapLayers(map);
 for(const id of ['rays','cones','baseline','corrected'])map.addSource('fusion-'+id,{type:'geojson',data:empty()});
 map.addLayer({id:'fusion-cones',type:'fill',source:'fusion-cones',paint:{'fill-color':'#faf0ae','fill-opacity':.10}});
 map.addLayer({id:'fusion-rays',type:'line',source:'fusion-rays',paint:{'line-color':'#faf0ae','line-width':2,'line-dasharray':[3,2]}});
 for(const [id,color] of [['baseline','#4aaf9b'],['corrected','#d25a9e']])map.addLayer({id:'fusion-'+id,type:'fill',source:'fusion-'+id,paint:{'fill-color':color,'fill-opacity':.35,'fill-outline-color':color}});
 for(const [id,coordinates] of Object.entries(positions))new maplibregl.Marker({color:'#7773a5'}).setLngLat(coordinates).setPopup(new maplibregl.Popup().setText(names[id]+' · candidate position, mounting and datum pending verification')).addTo(map);
 $('map-status').textContent='Terrain 1× · towers at candidate positions · the sightlines are directions, not fire positions.';render();});
map.on('click',e=>{if(!state.ready)return;const ids=[...state.layerControl.layerIds(),'fusion-rays','fusion-baseline','fusion-corrected'];const hit=map.queryRenderedFeatures(e.point,{layers:ids})[0];if(!hit)return;const name=['hotspots','arrival','perimeter'].find(n=>mapLayerId(n)===hit.layer.id);const lines=name?popupLines(name,hit.properties):hit.layer.id==='fusion-rays'?['EXPERIMENTAL camera sightline',hit.properties.observationId,'Drawing length: 30 km; not an estimated distance to the fire.']:['MODELLED scenario, not observed','Compare with the reference without cameras and the held-out metrics.'];const content=node('div');lines.forEach(line=>content.append(node('p',String(line))));new maplibregl.Popup({maxWidth:'320px'}).setLngLat(e.lngLat).setDOMContent(content).addTo(map);});
map.on('error',()=>{$('map-status').textContent='Some map tiles are not available; the experiment artefacts remain accessible.';});
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
async function get(url){const r=await fetch(url);const body=await r.json();if(!r.ok)throw Error(body.error||'Source not available.');return body;}
function timeOf(row){return Date.parse(row.timeUtcAssumed||'')/1000;}
function rows(){return state.fusion?.vision?.observations||[];}
function selected(camera){const available=rows().filter(o=>o.cameraId===camera&&o.method==='cosmos');
 if(!$('assume-pdt').checked)return available[0]||null;
 const near=available.filter(o=>Number.isFinite(timeOf(o))&&Math.abs(timeOf(o)-state.cursor)<=300);
 return near.sort((a,b)=>Math.abs(timeOf(a)-state.cursor)-Math.abs(timeOf(b)-state.cursor))[0]||null;}
function card(camera){const article=node('article',undefined,'camera'),row=selected(camera);article.append(node('h3',names[camera],'description'));
 if(!row){article.append(node('p',$('assume-pdt').checked?'No frame within ±5 min under the PDT assumption.':'No structured frames are available yet.','empty'));return article;}
 const img=node('img');img.src=row.imageUrl;img.alt=`${names[camera]} · ${printed(row.printedTime)} · ${row.poseId}`;article.append(img);
 const desc=node('div',undefined,'description');desc.append(node('strong',`Pose ${row.poseId} · ${printed(row.printedTime)}`));
 desc.append(node('p',row.base_visible?'Base marked in the image · inference pending review.':'Base not visible or not distinguishable: this observation does not correct the scenario.'));
 desc.append(node('p',row.reason||''),node('p',`Time ${row.printedTimeStatus||'unchecked'} · ${row.reviewStatus||'operator review pending'}. Uncalibrated model confidence: ${row.confidence??'—'}.`));
 if(row.base_visible&&Number.isFinite(row.x_base)&&Number.isFinite(row.y_base))desc.append(node('p',`Image mark: x ${(row.x_base*100).toFixed(1)}%, y ${(row.y_base*100).toFixed(1)}%. The mark is not a geographic coordinate.`));
 article.append(desc);return article;}
function endpoint(origin,bearing,metres){const angle=metres/6371000,br=bearing*Math.PI/180,lat=origin[1]*Math.PI/180,lon=origin[0]*Math.PI/180;
 const y=Math.asin(Math.sin(lat)*Math.cos(angle)+Math.cos(lat)*Math.sin(angle)*Math.cos(br));
 const x=lon+Math.atan2(Math.sin(br)*Math.sin(angle)*Math.cos(lat),Math.cos(angle)-Math.sin(lat)*Math.sin(y));return[x*180/Math.PI,y*180/Math.PI];}
function selectedModel(){const fusion=state.fusion,printed=$('camera-model').value==='printed';return{doc:printed?fusion?.printedModel:fusion?.calibration,current:printed?fusion?.printedModelArtifactCurrent:fusion?.calibrationArtifactCurrent,printed};}
function selectedScenario(){return $('camera-model').value==='printed'?state.fusion?.assimilation:state.fusion?.assimilationContrast;}
function visualRays(){const model=selectedModel();if(!$('assume-pdt').checked||!$('rays').checked||!model.current||(model.printed&&!$('assume-x').checked))return empty();const poses=model.doc?.poses||[];const features=[];
 for(const camera of Object.keys(positions)){const row=selected(camera);if(row?.base_visible!==true||!Number.isFinite(row.x_base)||row.x_base<0||row.x_base>1||row.printedTimeStatus!=='verified-by-agent'||row.clockStatus!=='assumed-PDT')continue;
 const pose=poses.find(p=>p.poseId===row.poseId&&p.cameraId===camera&&p.method===row.method&&p.status==='experimental');
 if(!pose||!Number.isFinite(pose.yaw0Deg)||!Number.isFinite(pose.fovDeg))continue;
 const bearing=pose.yaw0Deg+Math.atan((row.x_base-.5)*2*Math.tan(pose.fovDeg*Math.PI/360))*180/Math.PI;
 features.push({type:'Feature',geometry:{type:'LineString',coordinates:[positions[camera],endpoint(positions[camera],bearing,30000)]},properties:{cameraId:camera,observationId:row.id,dataClass:'experimental-camera-bearing',bearingDeg:bearing,angularHalfWidthDeg:pose.uncertainty?.suggestedAngularHalfWidthDeg,displayLengthM:30000,note:'Drawing length; not an estimated distance to the fire.'}});
 }return{type:'FeatureCollection',features};}
function cones(rays){return{type:'FeatureCollection',features:rays.features.filter(f=>Number.isFinite(f.properties.angularHalfWidthDeg)).map(f=>{const origin=f.geometry.coordinates[0],{bearingDeg,angularHalfWidthDeg}=f.properties;const arc=[];for(let i=0;i<=20;i++)arc.push(endpoint(origin,bearingDeg-angularHalfWidthDeg+2*angularHalfWidthDeg*i/20,30000));return{type:'Feature',properties:{...f.properties,dataClass:'experimental-angular-envelope-not-confidence-interval'},geometry:{type:'Polygon',coordinates:[[origin,...arc,origin]]}};})};}
function forecastData(kind){const doc=selectedScenario(),model=selectedModel();if(!$('forecast').checked||!doc||(kind==='corrected'&&(!$('assume-pdt').checked||!model.current||(model.printed&&!$('assume-x').checked))))return empty();
 const lead=Number($('lead').value),branch=doc[kind];
 const candidates=[...(Array.isArray(branch?.forecasts)?branch.forecasts:[]),...(Array.isArray(doc.forecasts)?doc.forecasts:[])];
 const match=candidates.find(f=>Number(f.leadMin??f.horizonMin)===lead&&(!f.variant||f.variant===kind));
 const geo=match?.geojson||match?.geometry||branch?.geojson;
 return geo?.type==='FeatureCollection'?geo:empty();}
function calibrationMetrics(pose){const wrapper=node('div');const half=pose.uncertainty?.suggestedAngularHalfWidthDeg;
 if(Number.isFinite(half))wrapper.append(node('p',selectedModel().printed?`Exploration width ±${half.toFixed(2)}°; assumed prior, not historical accuracy or a confidence interval.`:`Experimental angular band ±${half.toFixed(2)}°; not a confidence interval, and it excludes the held-out errors.`));
 const held=pose.errors?.heldOut||[];if(!held.length){wrapper.append(node('p',selectedModel().printed?'No usable observations in the check passes.':'No usable observations in the held-out passes.'));return wrapper;}
 const table=node('table'),head=node('tr');for(const label of [selectedModel().printed?'Check UTC':'Held-out UTC','Centroid error','Cross-track','Group dist.'])head.append(node('th',label));table.append(head);
 const num=(x,d=0)=>Number.isFinite(x)?Number(x).toFixed(d):'—';
 for(const pass of held){const row=node('tr');for(const text of [formatTimestamp(pass.passId?.split('@')[1]||pass.passId),`${num(pass.centroid?.absResidualDeg?.mean,2)}°`,`${num(pass.centroid?.crossTrackM?.mean)} m`,`${num(pass.nearestGroup?.crossTrackM?.mean)} m`])row.append(node('td',text));table.append(row);}
 wrapper.append(table,node('p','Compatibility with satellite detections, not absolute geolocation accuracy. Wide sectors can produce small group distances without identifying the same base.'));return wrapper;}
function renderEvaluation(){const fusion=state.fusion;if(!fusion)return;
 const model=selectedModel(),cal=model.doc||{},sim=selectedScenario()||{};const visible=rows().filter(o=>o.method==='cosmos'&&o.base_visible).length;
 $('gates').replaceChildren(...[
 `Observations: ${rows().filter(o=>o.method==='cosmos').length} · declared visible bases: ${visible} · operator review pending.`,
 `Camera model: ${cal.status||'no status'}. ${cal.statusDetail||cal.reason||''}${cal.status==='experimental'&&!model.current?' Artefact out of date or without integrity: sightlines disabled.':''}`,
 `Assimilation: ${sim.status||'no status'} · observations used: ${sim.cameraUseCount??'no result'}.`,
 $('assume-pdt').checked?'Exploration with an assumed PDT clock; not synchronised.':'The sightlines and the scenario with cameras are disabled until the clock hypothesis is explicitly chosen.',
 model.printed?'Primary: printed X as an assumed bearing, without a FIRMS fit. '+($('assume-x').checked?'Historical hypothesis enabled; not verified.':'Historical hypothesis disabled; sightlines and correction hidden.'):'Contrast: yaw fitted with training passes; only the held-out passes evaluate this fit.'
 ].map(t=>node('span',t,'pill')));
 $('assume-x').disabled=!model.printed;
 const poses=cal.poses||[];$('calibration').replaceChildren();
 if(!poses.length)$('calibration').append(node('p',cal.reason||'The fit is not available yet.'));
 for(const pose of poses){const section=node('div');section.append(node('strong',`${names[pose.cameraId]||pose.cameraId} · ${pose.poseId} · ${pose.method||'no observations'} · ${pose.status==='experimental'?(model.printed?'unfitted hypothesis':'experimental fit'):'no usable parameters'}`));
 if(Number.isFinite(pose.yaw0Deg))section.append(node('p',`Base bearing ${pose.yaw0Deg.toFixed(2)}° · FOV ${Number(pose.fovDeg).toFixed(2)}° (unverified prior).`));
 if(model.printed&&pose.satelliteValidationStatus==='not-observed-in-pose-window')section.append(node('p','No satellite pass for this pose: hypothetical bearing without satellite validation.'));
 if(Number.isFinite(pose.comparisonWithFit?.printedMinusFitDeg))section.append(node('p',`Difference X − fitted yaw: ${pose.comparisonWithFit.printedMinusFitDeg.toFixed(2)}°.`));
 if(pose.reason)section.append(node('p',pose.reason));if(pose.errors)section.append(calibrationMetrics(pose));$('calibration').append(section);}
 $('prediction').replaceChildren(node('p',sim.reason||'The reference without cameras is kept; a correction is shown only where there is support.'));
 if(sim.metrics)$('prediction').append(node('pre',JSON.stringify(sim.metrics,null,2)));
 if(Array.isArray(sim.limitations))for(const limitation of sim.limitations)$('prediction').append(node('p',limitation));
}
function render(){ $('clock').textContent=formatUtc(state.cursor);$('time').value=String(state.cursor);
 $('cameras').replaceChildren(...Object.keys(positions).map(card));renderEvaluation();
 const points=state.layers.hotspots?.features||[];const count=points.filter(f=>f.properties.t<=state.cursor&&f.properties.t>=state.cursor-43200).length;$('pass-count').textContent=`${count} thermal detections in the previous 12 h.`;
 $('weather').replaceChildren(...weatherLines(nearestWeatherHour(state.weather,state.cursor),state.weatherPoint).map(t=>node('div',t)));
 if(!state.ready)return;
 state.layerControl.setCursor(state.cursor);for(const name of ['hotspots','arrival','perimeter']){if($(name).checked&&state.layers[name])state.layerControl.show(name,state.layers[name]);else state.layerControl.hide(name);}
 const rays=visualRays();map.getSource('fusion-rays').setData(rays);map.getSource('fusion-cones').setData(cones(rays));map.getSource('fusion-baseline').setData(forecastData('baseline'));map.getSource('fusion-corrected').setData(forecastData('corrected'));
}
async function refresh(){ $('refresh').disabled=true;try{state.fusion=await get('/api/camera-fusion');render();}catch(e){$('gates').textContent=e.message;}finally{$('refresh').disabled=false;}}
$('refresh').onclick=refresh;for(const id of ['assume-pdt','camera-model','assume-x','hotspots','arrival','perimeter','rays','forecast','lead'])$(id).addEventListener('change',render);
$('time').addEventListener('input',()=>{state.cursor=Number($('time').value);render();});
$('export').onclick=()=>{if(!state.fusion)return;const record={...state.fusion,exportedAt:new Date().toISOString(),view:{cursorUtc:new Date(state.cursor*1000).toISOString(),assumePdt:$('assume-pdt').checked,assumeHistoricalX:$('assume-x').checked,cameraModel:$('camera-model').value,leadMin:Number($('lead').value)},note:'Experimental artefacts; the satellite sources remain in the Garnet package.'};
 const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='firetrace-camera-experiment.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
await refresh();
await Promise.allSettled(['hotspots','arrival','perimeter','weather','summary'].map(async name=>{try{const data=await get('/api/satellite?layer='+name);if(name==='weather'){state.weather=prepareWeather(data);state.weatherPoint=data.point;}else if(name==='summary'){state.summary=data;$('quality').replaceChildren(...evidenceWarnings(data).map(t=>node('li',t)));}else state.layers[name]=data;render();}catch(e){$('map-status').textContent=`The ${name} source is not available. The other layers remain accessible.`;}}));
