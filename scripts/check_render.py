"""Fail the build if the sole source workbook or application assets are missing."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))

from sqv.config import load_config
from sqv.load import load_products
from sqv.scenarios import build_cases
from sqv.engine import simulate


def main():
    for relative in ('app.py', 'assets/dashboard.css', '.streamlit/config.toml',
                     'configs/base.yaml', 'Matriz_15_productos_actualizada (1) (1).xlsx'):
        if not (ROOT/relative).is_file():
            raise FileNotFoundError(f'Falta un archivo requerido para Render: {relative}')
    config=load_config(ROOT/'configs/base.yaml')
    source=ROOT/config['fuente']['archivo']
    expected=ROOT/'Matriz_15_productos_actualizada (1) (1).xlsx'
    if source.resolve()!=expected.resolve():
        raise ValueError('La configuración debe usar únicamente el Excel original de los 15 productos')
    products=load_products(source,source='reference')
    cases=build_cases(products)
    if len(cases)!=405:
        raise ValueError(f'Se esperaban 405 casos; se encontraron {len(cases)}')
    for form in ('B','C'):
        for policy in ('P0','P1','P2','P3'):
            result=simulate(cases[0],policy,form)
            if result.sold+result.remaining!=cases[0].stock0:
                raise ArithmeticError('El control de inventario falló')
    print(f'Render OK: {len(products)} productos del Excel original, {len(cases)} casos, modelos B/C y políticas P0–P3.')


if __name__=='__main__':
    main()
