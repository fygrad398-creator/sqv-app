"""Importador auditable de matrices SQV: plantilla tecnica y Excel comercial original.

El archivo comercial contiene titulos en filas 1-2 y encabezados en fila 4,
no tiene columna ID y expresa W/bloques con unidades de texto. Se importa tal
como fue recibido, sin modificarlo ni inferir ventas, costes o stock mensual.
"""
from __future__ import annotations
import re
import unicodedata
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from .model import Product, ALPHA_BY_CATEGORY, WINDOW_BLOCKS


def norm(value: object) -> str:
    text = unicodedata.normalize('NFKD', str(value or '').strip().lower())
    text = ''.join(letter for letter in text if not unicodedata.combining(letter))
    return re.sub(r'[^a-z0-9]+', '_', text).strip('_')


COLUMNS = {
    'id': ('id', 'codigo', 'sku', 'id_producto', 'codigo_producto'),
    'name': ('nombre', 'producto', 'presentacion', 'descripcion', 'nombre_producto',
             'nombre_y_presentacion'),
    'category': ('categoria', 'grupo', 'familia', 'clasificacion'),
    'p0': ('precio', 'precio_regular', 'precio_venta', 'precio_soles', 'p0',
           'precio_s', 'precio_regular_s', 'precio_de_venta_s', 'precio_de_venta'),
    'life': ('vida_util', 'vida_util_dias', 'vida_dias', 'vida',
             'vida_util_dias_desde_la_expedicion_hasta_fecha_de_vencimiento'),
    'window': ('ventana', 'ventana_descuento', 'ventana_dias', 'dias_descuento',
               'ventana_de_descuento'),
    'blocks': ('subventanas', 'bloques', 'blocks', 'sub_ventanas'),
    'alpha': ('alpha', 'elasticidad', 'magnitud_elasticidad'),
    'beta': ('beta', 'frescura_beta'),
    'weight': ('peso', 'wi', 'w', 'peso_demanda'),
    'source': ('origen', 'fuente', 'source'),
}
REQUIRED = ('name', 'category', 'p0', 'life', 'window')


def category(value: str) -> str:
    aliases = {
        'panaderia': 'Panaderia', 'panaderia_y_pasteleria': 'Panaderia',
        'embutidos': 'Embutidos', 'lacteos': 'Lacteos', 'lacteo': 'Lacteos',
    }
    key = norm(value)
    if key not in aliases:
        raise ValueError(f'Categoria no reconocida: {value}')
    return aliases[key]


def as_number(value: object, field: str) -> float:
    if isinstance(value, str):
        text = value.strip().replace('S/', '').replace(' ', '')
        if ',' in text and '.' in text:
            text = text.replace('.', '').replace(',', '.') if text.rfind(',') > text.rfind('.') else text.replace(',', '')
        elif ',' in text:
            text = text.replace(',', '.')
        value = text
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'Numero invalido en {field}: {value!r}') from None
    if not pd.notna(result) or result in (float('inf'), float('-inf')):
        raise ValueError(f'Numero no finito en {field}: {value!r}')
    return result


def as_days(value: object, field: str) -> int:
    """Admite 3, 3.0, '3 dias', '10 días', sin aceptar fracciones."""
    if isinstance(value, str):
        match = re.fullmatch(r'\s*(\d+)\s*(?:d[ií]as?)?\s*', value, re.IGNORECASE)
        if match:
            return int(match.group(1))
    amount = as_number(value, field)
    if not amount.is_integer():
        raise ValueError(f'{field} debe contener dias enteros: {value!r}')
    return int(amount)


def parse_blocks(raw: object, window: int) -> tuple[int, ...]:
    """'1 dias' significa bloques diarios durante W; '4/3/3' es explicito."""
    if raw is None or (not isinstance(raw, (tuple, list)) and pd.isna(raw)):
        return WINDOW_BLOCKS[window]
    if isinstance(raw, (tuple, list)):
        values = tuple(as_days(x, 'subventanas') for x in raw)
    elif isinstance(raw, (int, float)):
        values = (as_days(raw, 'subventanas'),)
    else:
        clean = re.sub(r'\s*d[ií]as?\s*$', '', str(raw).strip(), flags=re.IGNORECASE)
        if not re.fullmatch(r'\s*\d+(?:\s*[/,;| -]\s*\d+)*\s*', clean):
            raise ValueError(f'Subventanas no reconocidas: {raw!r}')
        values = tuple(int(n) for n in re.findall(r'\d+', clean))
    if len(values) == 1:
        day_count = values[0]
        if day_count < 1 or window % day_count:
            raise ValueError(f'Subventana de {day_count} dias no divide ventana de {window}')
        values = (day_count,) * (window // day_count)
    if any(v <= 0 for v in values) or sum(values) != window:
        raise ValueError(f'Bloques {values} no suman ventana de {window} dias')
    return values


def _column_matches(headers: list[object]) -> dict[str, int | None]:
    keys = [norm(x) for x in headers]
    found = {}
    for field, aliases in COLUMNS.items():
        found[field] = next((j for j, key in enumerate(keys) if key in aliases), None)
    return found


def _read_matrix(path: Path) -> tuple[pd.DataFrame, dict[str, int | None], str]:
    if path.suffix.lower() in ('.xlsx', '.xlsm'):
        raw = pd.read_excel(path, sheet_name='Matriz_15', header=None, engine='openpyxl')
        # Algunas matrices llevan titulo, subtitulo y una fila de separacion.
        for header_idx in range(min(len(raw), 40)):
            fields = _column_matches(list(raw.iloc[header_idx]))
            if all(fields[k] is not None for k in REQUIRED):
                result = raw.iloc[header_idx + 1:].copy()
                result['__source_row__'] = [int(i) + 1 for i in result.index]
                return result, fields, 'Matriz_15'
        raise ValueError('No se encontraron encabezados de Categoria, Nombre, Precio, Vida util y Ventana en Matriz_15')
    if path.suffix.lower() == '.csv':
        df = pd.read_csv(path, encoding='utf-8-sig')
        fields = _column_matches(list(df.columns))
        if not all(fields[k] is not None for k in REQUIRED):
            raise ValueError(f'Faltan columnas de matriz: {[k for k in REQUIRED if fields[k] is None]}')
        df['__source_row__'] = [i + 2 for i in range(len(df))]
        return df, fields, 'CSV'
    raise ValueError('Solo se admiten archivos Excel .xlsx/.xlsm o CSV')


def read_alpha_anchors(path: str | Path) -> dict[str, float]:
    """Recupera los anclajes que aparecen en Presentacion!D11:D13, si existen."""
    result = dict(ALPHA_BY_CATEGORY)
    path = Path(path)
    if path.suffix.lower() not in ('.xlsx', '.xlsm'):
        return result
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        if 'Presentacion' not in book.sheetnames:
            return result
        sheet = book['Presentacion']
        for row in sheet.iter_rows(min_row=1, max_col=4, values_only=True):
            if row[0] is None or row[3] is None:
                continue
            try:
                key = category(str(row[0]))
            except ValueError:
                continue
            result[key] = as_number(row[3], f'elasticidad Presentacion/{key}')
            if result[key] <= 0:
                raise ValueError(f'Elasticidad no positiva en Presentacion/{key}')
    finally:
        book.close()
    return result


def load_products(path: str | Path, *, source: str = 'reference') -> list[Product]:
    """Lee exactamente 15 productos desde el Excel tal cual, sin crear registros ficticios.

    'reference' indica precios de referencia y configuraciones pendientes de
    validacion, NO ventas/inventarios observados ni elasticidades por SKU.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'No se encuentra matriz: {path}')
    frame, fields, sheet = _read_matrix(path)
    # Solo eliminar filas totalmente vacias en los campos realmente usados.
    frame = frame.loc[frame.iloc[:, fields['name']].notna() |
                      frame.iloc[:, fields['category']].notna()].copy()
    if len(frame) != 15:
        raise ValueError(f'Se esperaban 15 productos; se encontraron {len(frame)}')
    anchors = read_alpha_anchors(path)
    products: list[Product] = []
    for ordinal, (_, row) in enumerate(frame.iterrows(), start=1):
        def get(field: str):
            col = fields[field]
            return row.iloc[col] if col is not None else None

        excel_row = int(row['__source_row__'])
        try:
            cat = category(str(get('category')))
            window = as_days(get('window'), 'ventana')
            if window not in WINDOW_BLOCKS:
                raise ValueError(f'Ventana {window} fuera de 2/3/10/15 dias')
            name = str(get('name')).strip()
            raw_id = get('id')
            identifier = (str(raw_id).strip() if raw_id is not None and pd.notna(raw_id)
                          and str(raw_id).strip() else f'SQV{ordinal:03d}')
            a, beta, weight, src = (get(f) for f in ('alpha', 'beta', 'weight', 'source'))
            flagged = cat == 'Lacteos' and ('keke' in norm(name) or 'marmoleado' in norm(name))
            product = Product(
                id=identifier, name=name, category=cat,
                p0=as_number(get('p0'), 'precio de venta'),
                life=as_days(get('life'), 'vida util'), window=window,
                blocks=parse_blocks(get('blocks'), window),
                alpha=anchors[cat] if a is None or pd.isna(a) else as_number(a, 'alpha'),
                beta=2.0 if beta is None or pd.isna(beta) else as_number(beta, 'beta'),
                weight=1.0 if weight is None or pd.isna(weight) else as_number(weight, 'wi'),
                source=str(src).strip() if src is not None and pd.notna(src) and str(src).strip() else source,
                sensitivity_flag=flagged,
            )
            products.append(product)
        except Exception as exc:
            raise ValueError(f'{sheet}, fila {excel_row}, producto {ordinal}: {exc}') from exc
    if len(set(p.id for p in products)) != len(products):
        raise ValueError('Los ID/SKU generados o recibidos deben ser unicos')
    counts = {cat: sum(p.category == cat for p in products) for cat in ALPHA_BY_CATEGORY}
    if counts != {'Panaderia': 6, 'Embutidos': 5, 'Lacteos': 4}:
        raise ValueError(f'Conteos por categoria diferentes del PDF: {counts}')
    return products
