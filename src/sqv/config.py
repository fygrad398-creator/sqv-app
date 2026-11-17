"""Read the experiment configuration and validate the guide's closed decisions."""
from pathlib import Path
import math
import yaml
from .model import DISCOUNTS, FORMS, POLICIES, SCENARIO_K, SCENARIO_S, SCALE_LAMBDA


def load_config(path):
    with Path(path).open(encoding='utf-8') as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict) or not isinstance(config.get('experimento'), dict):
        raise ValueError('Configuración sin sección experimento')
    e = config['experimento']
    for key, expected in [('rotation_k', SCENARIO_K), ('stock_s', SCENARIO_S),
                          ('funciones', FORMS), ('politicas', POLICIES),
                          ('descuentos_p3', DISCOUNTS)]:
        if tuple(e[key]) != expected:
            raise ValueError(f'{key} debe respetar las decisiones cerradas de la guía: {expected}')
    if e['lambda_por_escala'] != SCALE_LAMBDA:
        raise ValueError('Las escalas de referencia deben ser 5, 15 y 30')
    for key in ('theta', 'beta_central', 'tolerancia_relativa_ic', 'tolerancia_absoluta_diferencias_soles'):
        value = float(e[key])
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key} debe ser finito y positivo')
    stages = e['niveles_replicas']
    if not stages or any(type(n) is not int or n < 2 for n in stages) or any(b <= a for a,b in zip(stages,stages[1:])):
        raise ValueError('niveles_replicas debe contener enteros crecientes de al menos 2')
    return config
