"""Fixed visual-observation task and strict parser; confidence is not calibrated accuracy."""
import json
import math
import re

TASK = 'smoke-base-v1'
PROMPT = '''Inspect this camera frame. Return only one JSON object with exactly these fields:
{"smoke":true,"base_visible":false,"x_base":null,"y_base":null,"confidence":0.0,"reason":"brief visible evidence and obstruction"}.
smoke and base_visible must be booleans. x_base and y_base are normalized image coordinates (0 left/top, 1 right/bottom) of ONE dominant smoke/fire base at its visible contact with terrain. Never select the plume top or infer a hidden base behind a ridge or smoke. If the ground contact is not visibly distinguishable, base_visible=false and both coordinates=null. If multiple unrelated bases cannot be distinguished, abstain. confidence is your uncalibrated assessment from 0 to 1, not a probability of geographic accuracy. Do not infer geography, range, temperature, speed, future spread or timestamps. Describe ambiguity in reason. Logos and overlays are not fire evidence.'''


def parse_observation(content):
    text=content.strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    row=json.loads(text)
    required = ['smoke','base_visible','x_base','y_base','confidence','reason']
    if not isinstance(row,dict) or any(key not in row for key in required):
        raise ValueError('La observación no incluye todos los campos obligatorios.')
    if any(type(row.get(key)) is not bool for key in ['smoke','base_visible']):
        raise ValueError('La observación requiere booleanos explícitos.')
    confidence=row.get('confidence')
    if isinstance(confidence,bool) or not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0<=confidence<=1:
        raise ValueError('Confianza fuera del intervalo permitido.')
    for key in ['x_base','y_base']:
        value=row.get(key)
        if row['base_visible']:
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=1:
                raise ValueError('Coordenada de imagen fuera del intervalo permitido.')
        elif value is not None:
            raise ValueError('Una base oculta no tiene coordenadas observadas.')
    if not isinstance(row.get('reason'),str) or len(row['reason'])>2000:
        raise ValueError('Falta la explicación visual de la observación.')
    return {key:row[key] for key in ['smoke','base_visible','x_base','y_base','confidence','reason']}
