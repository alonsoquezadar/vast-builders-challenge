"""Read experimental worker artifacts while they are produced; never invent readiness."""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).parent
EXPERIMENT=ROOT/'camera_assimilation'


def _document(path):
    if not path.is_file():return {'status':'pending-input','reason':'El artefacto todavía no está disponible.'}
    try:
        raw=path.read_bytes();doc=json.loads(raw)
    except (OSError,ValueError):return {'status':'pending-input','reason':'El artefacto todavía no está completo.'}
    if not isinstance(doc,dict):return {'status':'invalid-artifact','reason':'Se esperaba un objeto JSON.'}
    return {**doc,'artifactSha256':hashlib.sha256(raw).hexdigest()}


def checked_observations(root=None):
    root=Path(root) if root else ROOT
    data=_document(root/'camera_assimilation/vision/observations.json')
    checked=[];issues=[];ids=set()
    records=data.get('observations',[])
    if not isinstance(records,list):
        return {**data,'status':'invalid-artifact','observations':[],'integrityIssues':[{'reason':'La colección de observaciones debe ser una lista.'}]}
    for row in records:
        try:
            if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in ids:raise ValueError('Identificador inválido o repetido.')
            ids.add(row['id'])
            path=(root/row['imagePath']).resolve()
            if not path.is_relative_to((root/'camera_assimilation/vision').resolve()):raise ValueError('Fotograma fuera de la carpeta autorizada.')
            if path.suffix.lower() not in ('.jpg','.jpeg','.png') or hashlib.sha256(path.read_bytes()).hexdigest()!=row['imageSha256']:raise ValueError('El fotograma no coincide con su huella.')
            checked.append({**row,'imageUrl':'/api/camera-frame?id='+quote(row['id'],safe=''),'frameIntegrity':'matched'})
        except (KeyError,ValueError,OSError,TypeError) as error:
            issues.append({'id':row.get('id') if isinstance(row,dict) else None,'reason':str(error) if isinstance(error,ValueError) else 'Falta el fotograma o su recibo.'})
    return {**data,'observations':checked,'integrityIssues':issues}


def load_camera_bundle(root=None):
    root=Path(root) if root else ROOT
    experiment=root/'camera_assimilation'
    vision=checked_observations(root)
    calibration=_document(experiment/'calibration/calibration.json')
    inputs=calibration.get('inputs',{}).get('observations',{})
    current=bool(vision.get('artifactSha256') and inputs.get('sha256')==vision['artifactSha256'] and not vision['integrityIssues'])
    printed=_document(experiment/'calibration/printed_model.json')
    printed_input=printed.get('inputs',{}).get('observations',{})
    printed_current=bool(vision.get('artifactSha256') and printed_input.get('sha256')==vision['artifactSha256'] and not vision['integrityIssues'])
    return {'schema':'firetrace-camera-fusion-v1','mode':'retrospective-experiment','operationallyValidated':False,
            'clockStatus':'assumed-PDT-not-verified','vision':vision,
            'calibrationArtifactCurrent':current, 'calibration':calibration,
            'printedModelArtifactCurrent':printed_current, 'printedModel':printed,
            'assimilation':_document(experiment/'assimilation/scenario.json'),
            'assimilationContrast':_document(experiment/'assimilation/scenario-fitted.json'),
            'limitations':['Reloj y posiciones de torre aún no verificados.',
                           'La inicialización reconstruida incorpora conocimiento posterior del incendio.',
                           'La revisión por operador está pendiente salvo que conste explícitamente en cada observación.']}


def camera_frame(identifier,root=None):
    root=Path(root) if root else ROOT
    rows=checked_observations(root)['observations']
    row=next((r for r in rows if r['id']==identifier),None)
    if row is None:raise ValueError('Fotograma no disponible o sin integridad verificada.')
    path=root/row['imagePath'];raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=row['imageSha256']:raise ValueError('El fotograma ha cambiado.')
    return raw,('image/png' if path.suffix.lower()=='.png' else 'image/jpeg')
