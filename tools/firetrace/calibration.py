"""Experimental fixed-origin camera fit. Reprojection is not geographic validation."""
import math


def fit_camera(data):
    import numpy as np
    from scipy.optimize import least_squares

    width, height = data.get('width'), data.get('height')
    origin = data.get('origin')
    points = data.get('points')
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)) or not 100 <= width <= 8192 or not 100 <= height <= 8192:
        raise ValueError('Dimensiones de imagen inválidas.')
    if not isinstance(origin, list) or len(origin) != 3 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in origin):
        raise ValueError('Se requiere posición y elevación de cámara.')
    if not -180 <= origin[0] <= 180 or not -85 <= origin[1] <= 85 or not -500 <= origin[2] <= 10000:
        raise ValueError('Posición de cámara inválida.')
    if not isinstance(points, list) or not 8 <= len(points) <= 40:
        raise ValueError('Añade al menos 6 referencias de ajuste y 2 de comprobación.')
    xyz, pixels, held = [], [], []
    for point in points:
        pixel, world = point.get('pixel'), point.get('world')
        if not isinstance(pixel, list) or len(pixel) != 2 or not isinstance(world, list) or len(world) != 3:
            raise ValueError('Cada referencia necesita píxel y coordenadas con elevación.')
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in pixel + world):
            raise ValueError('Referencia no finita.')
        if not 0 <= pixel[0] <= width or not 0 <= pixel[1] <= height or not -180 <= world[0] <= 180 or not -85 <= world[1] <= 85 or not -500 <= world[2] <= 10000:
            raise ValueError('Referencia fuera de límites.')
        east = math.radians(world[0] - origin[0]) * 6371000 * math.cos(math.radians(origin[1]))
        north = math.radians(world[1] - origin[1]) * 6371000
        radius = math.hypot(east, north)
        if not 100 <= radius <= 50000:
            raise ValueError('Usa referencias situadas entre 100 m y 50 km de la cámara.')
        xyz.append([east, north, world[2] - origin[2] - radius ** 2 / (2 * 6371000)])
        pixels.append(pixel)
        held.append(point.get('role') == 'check')
    xyz, pixels, held = np.array(xyz), np.array(pixels), np.array(held)
    train = ~held
    if train.sum() < 6 or held.sum() < 2:
        raise ValueError('Se requieren 6 referencias de ajuste y 2 de comprobación separadas.')
    if np.ptp(pixels[train, 0]) < width * .25 or np.ptp(pixels[train, 1]) < height * .03:
        raise ValueError('Distribuye las referencias por la imagen, con separación horizontal y vertical.')

    def project(params):
        yaw, pitch, roll, log_focal = params
        right = np.array([math.cos(yaw), -math.sin(yaw), 0])
        forward = np.array([math.sin(yaw) * math.cos(pitch), math.cos(yaw) * math.cos(pitch), math.sin(pitch)])
        down = np.cross(forward, right)
        r = math.cos(roll) * right + math.sin(roll) * down
        d = -math.sin(roll) * right + math.cos(roll) * down
        depth = xyz @ forward
        safe_depth = np.maximum(depth, 1)
        focal = math.exp(log_focal)
        return np.column_stack([width / 2 + focal * (xyz @ r) / safe_depth,
                                height / 2 + focal * (xyz @ d) / safe_depth]), depth

    yaw0 = math.atan2(float(np.mean(xyz[train, 0])), float(np.mean(xyz[train, 1])))
    initial = [yaw0, 0, 0, math.log(width)]
    result = least_squares(lambda p: (project(p)[0][train] - pixels[train]).ravel(), initial,
                           bounds=([yaw0-1.4, -.7, -.5, math.log(width*.25)],
                                   [yaw0+1.4, .7, .5, math.log(width*10)]), loss='soft_l1', f_scale=3,
                           max_nfev=1500)
    projected, depth = project(result.x)
    if not result.success or np.any(depth <= 0):
        raise ValueError('No se pudo ajustar una cámara que observe todas las referencias.')
    errors = np.linalg.norm(projected - pixels, axis=1)
    yaw, pitch, roll, log_focal = result.x
    return {'status': 'fitted-unvalidated', 'origin': origin,
            'yawDeg': math.degrees(yaw) % 360, 'pitchDeg': math.degrees(pitch),
            'rollDeg': math.degrees(roll), 'horizontalFovDeg': math.degrees(2*math.atan(width/(2*math.exp(log_focal)))),
            'fitRmsPx': float(np.sqrt(np.mean(errors[train]**2))),
            'checkRmsPx': float(np.sqrt(np.mean(errors[held]**2))),
            'projectedPixels': projected.tolist(), 'errorsPx': errors.tolist(),
            'limitations': ['Posición de cámara fija y no validada; coordenadas públicas redondeadas.',
                            'Modelo local sin refracción, distorsión óptica ni ajuste de posición.',
                            'Error en píxeles no equivale a precisión geográfica.',
                            'No se proyecta humo elevado sobre el suelo.']}
