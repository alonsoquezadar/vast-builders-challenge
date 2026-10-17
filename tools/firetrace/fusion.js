import {createMapLayers,prepareWeather,nearestWeatherHour,weatherLines,evidenceWarnings,formatUtc,popupLines,mapLayerId} from './satellite-view.mjs';
const $=id=>document.getElementById(id), empty=()=>({type:'FeatureCollection',features:[]});
const positions={delilah:[-119.1175,36.80417],buckrock:[-118.86067,36.73727]};
const names={delilah:'Delilah Lookout 2',buckrock:'Buck Rock 1'};
const state={fusion:null,layers:{},weather:[],summary:null,ready:false,layerControl:null,cursor:Date.parse('2025-08-27T19:49:00Z')/1000};
const map=new maplibregl.Map({container:'map',center:[-119.035,36.87],zoom:10.8,pitch:55,bearing:-20,style:{version:8,sources:{imagery:{type:'raster',tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],tileSize:256,attribution:'Imagery © Esri & contributors'},terrain:{type:'raster-dem',tiles:['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'],tileSize:256,encoding:'terrarium',maxzoom:15,attribution:'Elevation: AWS Terrain Tiles'}},layers:[{id:'imagery',type:'raster',source:'imagery'}]}});
map.addControl(new maplibregl.NavigationControl());map.addControl(new maplibregl.ScaleControl());
map.on('load',()=>{state.ready=true;map.setTerrain({source:'terrain',exaggeration:1});state.layerControl=createMapLayers(map);
 for(const id of ['rays','baseline','corrected'])map.addSource('fusion-'+id,{type:'geojson',data:empty()});
 map.addLayer({id:'fusion-rays',type:'line',source:'fusion-rays',paint:{'line-color':'#faf0ae','line-width':2,'line-dasharray':[3,2]}});
 for(const [id,color] of [['baseline','#4aaf9b'],['corrected','#d25a9e']])map.addLayer({id:'fusion-'+id,type:'fill',source:'fusion-'+id,paint:{'fill-color':color,'fill-opacity':.35,'fill-outline-color':color}});
 for(const [id,coordinates] of Object.entries(positions))new maplibregl.Marker({color:'#7773a5'}).setLngLat(coordinates).setPopup(new maplibregl.Popup().setText(names[id]+' · posición candidata, montaje y datum pendientes de verificar')).addTo(map);
 $('map-status').textContent='Relieve 1× · torres en posición candidata · las visuales son direcciones, no posiciones de fuego.';render();});
map.on('click',e=>{if(!state.ready)return;const ids=[...state.layerControl.layerIds(),'fusion-rays','fusion-baseline','fusion-corrected'];const hit=map.queryRenderedFeatures(e.point,{layers:ids})[0];if(!hit)return;const name=['hotspots','arrival','perimeter'].find(n=>mapLayerId(n)===hit.layer.id);const lines=name?popupLines(name,hit.properties):hit.layer.id==='fusion-rays'?['Visual de cámara EXPERIMENTAL',hit.properties.observationId,'Longitud de dibujo: 30 km; no es una distancia estimada al fuego.']:['Escenario MODELADO, no observado','Comparar con referencia sin cámaras y métricas reservadas.'];const content=node('div');lines.forEach(line=>content.append(node('p',String(line))));new maplibregl.Popup({maxWidth:'320px'}).setLngLat(e.lngLat).setDOMContent(content).addTo(map);});
map.on('error',()=>{$('map-status').textContent='Alguna tesela no está disponible; los artefactos del experimento siguen accesibles.';});
function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
async function get(url){const r=await fetch(url);const body=await r.json();if(!r.ok)throw Error(body.error||'Fuente no disponible.');return body;}
function timeOf(row){return Date.parse(row.timeUtcAssumed||'')/1000;}
function rows(){return state.fusion?.vision?.observations||[];}
function selected(camera){const available=rows().filter(o=>o.cameraId===camera&&o.method==='cosmos');
 if(!$('assume-pdt').checked)return available[0]||null;
 const near=available.filter(o=>Number.isFinite(timeOf(o))&&Math.abs(timeOf(o)-state.cursor)<=300);
 return near.sort((a,b)=>Math.abs(timeOf(a)-state.cursor)-Math.abs(timeOf(b)-state.cursor))[0]||null;}
function card(camera){const article=node('article',undefined,'camera'),row=selected(camera);article.append(node('h3',names[camera],'description'));
 if(!row){article.append(node('p',$('assume-pdt').checked?'Sin fotograma a ±5 min bajo el supuesto PDT.':'Todavía no hay fotogramas estructurados disponibles.','empty'));return article;}
 const img=node('img');img.src=row.imageUrl;img.alt=`${names[camera]} · ${row.printedTime} · ${row.poseId}`;article.append(img);
 const desc=node('div',undefined,'description');desc.append(node('strong',`Pose ${row.poseId} · ${row.printedTime}`));
 desc.append(node('p',row.base_visible?'Base marcada en la imagen · inferencia pendiente de revisión.':'Base no visible o no distinguible: esta observación no corrige el escenario.'));
 desc.append(node('p',row.reason||''),node('p',`Hora ${row.printedTimeStatus||'sin comprobar'} · ${row.reviewStatus||'revisión por operador pendiente'}. Confianza del modelo no calibrada: ${row.confidence??'—'}.`));
 if(row.base_visible&&Number.isFinite(row.x_base)&&Number.isFinite(row.y_base))desc.append(node('p',`Marca de imagen: x ${(row.x_base*100).toFixed(1)}%, y ${(row.y_base*100).toFixed(1)}%. La marca no es una coordenada geográfica.`));
 article.append(desc);return article;}
function endpoint(origin,bearing,metres){const angle=metres/6371000,br=bearing*Math.PI/180,lat=origin[1]*Math.PI/180,lon=origin[0]*Math.PI/180;
 const y=Math.asin(Math.sin(lat)*Math.cos(angle)+Math.cos(lat)*Math.sin(angle)*Math.cos(br));
 const x=lon+Math.atan2(Math.sin(br)*Math.sin(angle)*Math.cos(lat),Math.cos(angle)-Math.sin(lat)*Math.sin(y));return[x*180/Math.PI,y*180/Math.PI];}
function visualRays(){if(!$('assume-pdt').checked||!$('rays').checked)return empty();const poses=state.fusion?.calibration?.poses||[];const features=[];
 for(const camera of Object.keys(positions)){const row=selected(camera);if(!row?.base_visible||!Number.isFinite(row.x_base)||row.printedTimeStatus==='uncertain')continue;
 const pose=poses.find(p=>p.poseId===row.poseId&&p.cameraId===camera);
 if(!pose||!Number.isFinite(pose.yaw0Deg)||!Number.isFinite(pose.fovDeg))continue;
 const bearing=pose.yaw0Deg+Math.atan((row.x_base-.5)*2*Math.tan(pose.fovDeg*Math.PI/360))*180/Math.PI;
 features.push({type:'Feature',geometry:{type:'LineString',coordinates:[positions[camera],endpoint(positions[camera],bearing,30000)]},properties:{cameraId:camera,observationId:row.id,dataClass:'experimental-camera-bearing',bearingDeg:bearing,displayLengthM:30000,note:'Longitud de dibujo; no es una distancia estimada al fuego.'}});
 }return{type:'FeatureCollection',features};}
function forecastData(kind){const doc=state.fusion?.assimilation;if(!$('forecast').checked||!$('assume-pdt').checked||!doc)return empty();
 const lead=Number($('lead').value),branch=doc[kind];
 const candidates=[...(Array.isArray(branch?.forecasts)?branch.forecasts:[]),...(Array.isArray(doc.forecasts)?doc.forecasts:[])];
 const match=candidates.find(f=>Number(f.leadMin??f.horizonMin)===lead&&(!f.variant||f.variant===kind));
 const geo=match?.geojson||match?.geometry||branch?.geojson;
 return geo?.type==='FeatureCollection'?geo:empty();}
function renderEvaluation(){const fusion=state.fusion;if(!fusion)return;
 const cal=fusion.calibration,sim=fusion.assimilation;const visible=rows().filter(o=>o.method==='cosmos'&&o.base_visible).length;
 $('gates').replaceChildren(...[
 `Observaciones: ${rows().filter(o=>o.method==='cosmos').length} · bases visibles declaradas: ${visible} · revisión por operador pendiente.`,
 `Calibración: ${cal.status||'sin estado'}. ${cal.reason||''}`,
 `Asimilación: ${sim.status||'sin estado'} · observaciones utilizadas: ${sim.cameraUseCount??'sin resultado'}.`,
 $('assume-pdt').checked?'Exploración con reloj PDT supuesto; no sincronizado.':'Las visuales y el escenario con cámaras están desactivados hasta elegir explícitamente la hipótesis de reloj.'
 ].map(t=>node('span',t,'pill')));
 const poses=cal.poses||[];$('calibration').replaceChildren();
 if(!poses.length)$('calibration').append(node('p',cal.reason||'El ajuste todavía no está disponible.'));
 for(const pose of poses){const section=node('div');section.append(node('strong',`${names[pose.cameraId]||pose.cameraId} · ${pose.poseId} · ${pose.status||'experimental'}`));
 if(Number.isFinite(pose.yaw0Deg))section.append(node('p',`Rumbo base ${pose.yaw0Deg.toFixed(2)}° · FOV ${Number(pose.fovDeg).toFixed(2)}° (prior sin verificar).`));
 if(pose.reason)section.append(node('p',pose.reason));if(pose.errors)section.append(node('pre',JSON.stringify(pose.errors,null,2)));$('calibration').append(section);}
 $('prediction').replaceChildren(node('p',sim.reason||'Se conserva la referencia sin cámaras; una corrección solo se muestra cuando existe soporte.'));
 if(sim.metrics)$('prediction').append(node('pre',JSON.stringify(sim.metrics,null,2)));
 if(Array.isArray(sim.limitations))for(const limitation of sim.limitations)$('prediction').append(node('p',limitation));
}
function render(){ $('clock').textContent=formatUtc(state.cursor);$('time').value=String(state.cursor);
 $('cameras').replaceChildren(...Object.keys(positions).map(card));renderEvaluation();
 const points=state.layers.hotspots?.features||[];const count=points.filter(f=>f.properties.t<=state.cursor&&f.properties.t>=state.cursor-43200).length;$('pass-count').textContent=`${count} detecciones térmicas en las 12 h previas.`;
 $('weather').replaceChildren(...weatherLines(nearestWeatherHour(state.weather,state.cursor),state.weatherPoint).map(t=>node('div',t)));
 if(!state.ready)return;
 state.layerControl.setCursor(state.cursor);for(const name of ['hotspots','arrival','perimeter']){if($(name).checked&&state.layers[name])state.layerControl.show(name,state.layers[name]);else state.layerControl.hide(name);}
 map.getSource('fusion-rays').setData(visualRays());map.getSource('fusion-baseline').setData(forecastData('baseline'));map.getSource('fusion-corrected').setData(forecastData('corrected'));
}
async function refresh(){ $('refresh').disabled=true;try{state.fusion=await get('/api/camera-fusion');render();}catch(e){$('gates').textContent=e.message;}finally{$('refresh').disabled=false;}}
$('refresh').onclick=refresh;for(const id of ['assume-pdt','hotspots','arrival','perimeter','rays','forecast','lead'])$(id).addEventListener('change',render);
$('time').addEventListener('input',()=>{state.cursor=Number($('time').value);render();});
$('export').onclick=()=>{if(!state.fusion)return;const record={...state.fusion,exportedAt:new Date().toISOString(),view:{cursorUtc:new Date(state.cursor*1000).toISOString(),assumePdt:$('assume-pdt').checked,leadMin:Number($('lead').value)},note:'Artefactos experimentales; las fuentes satelitales permanecen en el paquete Garnet.'};
 const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));const a=node('a');a.href=url;a.download='firetrace-camera-experiment.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
await refresh();
await Promise.allSettled(['hotspots','arrival','perimeter','weather','summary'].map(async name=>{try{const data=await get('/api/satellite?layer='+name);if(name==='weather'){state.weather=prepareWeather(data);state.weatherPoint=data.point;}else if(name==='summary'){state.summary=data;$('quality').replaceChildren(...evidenceWarnings(data).map(t=>node('li',t)));}else state.layers[name]=data;render();}catch(e){$('map-status').textContent=`La fuente ${name} no está disponible. Las otras capas siguen accesibles.`;}}));
