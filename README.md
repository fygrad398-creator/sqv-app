# SQV 1.2 · Laboratorio de descuentos

**Optimización de estrategias de descuentos para productos perecederos**  
Proyecto de investigación computacional | comercio minorista peruano | 17/11/2026

El laboratorio SQV **carga por defecto la matriz comercial de 15 productos proporcionada** y aplica la guía de programación de cuatro páginas y el resumen de proyecto de dos páginas.

La revisión 1.2 renueva el diseño del panel y del visor autónomo, incorpora parada adaptativa hasta 100.000 réplicas en el panel, configuración YAML activa, pruebas cruzadas B↔C, sensibilidad de los kekes y descarga del expediente experimental en ZIP. Pasaron 50 pruebas; se ejecutaron las 3.240 evaluaciones deterministas y los barridos completos de sensibilidad y calibración cruzada. El detalle y los pendientes científicos están en [la revisión de requisitos](docs/REVISION_GUIA_Y_DISENO_V12.md).

**Para ver el nuevo diseño sin instalar nada:** abrir [Vista_previa_SQV.html](Vista_previa_SQV.html). Para ejecutar nuevas simulaciones, usar los iniciadores indicados a continuación.

**Para publicar el panel en Render:** usa `render.yaml` y sigue [la guía de despliegue](docs/DESPLIEGUE_RENDER.md). `SQV_Render.zip` contiene el paquete de despliegue con el Excel original. El Blueprint configura un servicio Python de una instancia y 2 GB de memoria, de pago; revisa el plan antes de desplegar.

> **Estado científico:** Matriz comercial de **referencia preliminar**, no registro completo de ventas observadas. Los resultados son experimentos simulados que **no** demuestran causalidad ni constituyen pérdidas contables reales.

## 1. Cómo iniciar

Necesitas **Python 3.11 o superior** e Internet solo para instalar dependencias inicialmente.

**Windows:** abre la carpeta extraída, haz doble clic en `INICIAR_WINDOWS.bat` (si falta alguna biblioteca, ejecuta primero el paso de instalación siguiente).

**macOS/Linux:** desde una terminal de la carpeta extraída, ejecuta `sh INICIAR_MAC_LINUX.sh`.

**Instalación alternativa (cualquier sistema):**

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

La dirección local que indique Streamlit abre el **panel interactivo de 8 pestañas**. La fuente única del panel es `Matriz_15_productos_actualizada (1) (1).xlsx`, hoja `Matriz_15`. No hay selector de demos ni carga de otras matrices. Se conservan los precios, vidas útiles, ventanas y bloques del Excel.

**Para cambiar los resultados:** selecciona producto, escala, escenario y modelo en «02 · Caso experimental». La vista **Determinista** se recalcula al cambiar el caso. Para demanda aleatoria, configura «03 · Monte Carlo» y pulsa **Aplicar cambios y ejecutar Monte Carlo**; la vista cambia a Monte Carlo y muestra pérdidas medias arriba, en «05 Resultados» y en «06 Estadística». Si cambias parámetros, aparece «pendiente de actualizar» hasta volver a ejecutar. La vista HTML sin instalación solo muestra resultados deterministas.

## 2. Qué se ajustó con los archivos recibidos

| Elemento | Comportamiento en v1.2 |
| --- | --- |
| `data/Matriz_15_productos_fuente.xlsx` | Copia íntegra del Excel recibido. Sin alterar datos ni formatos. |
| Lectura de `Matriz_15` | Detecta encabezados en fila 4, columnas en español, tildes y campos opcionales. |
| Identificador | Genera `SQV001` a `SQV015` por orden de filas si no hay columna ID. |
| Ventanas del Excel | Lee `2 dias`, `3 dias`, `10 días`, `15 días`. |
| Subventanas | `1 días` significa bloques diarios (2 o 3); también `4/3/3` y `6/5/4`. |
| Precio y vida útil | Toma el valor de cada producto tal cual figura en el Excel, sin sustituirlo. La vida útil requiere verificación documental. |
| Elasticidades alfa | Lee los anclajes de la pestaña `Presentacion`: Panadería 0.81, Embutidos 0.73, Lácteos 1.02. Son **referencias de grupo**, no elasticidades promocionales observadas por producto. |
| Clasificación de los kekes | Conserva 2 productos en Lácteos tal como indica el Excel, pero señala la clasificación para revisión. |
| Stock de las capturas | No se usa para calibrar `lambda` ni como stock mensual. El inventario inicial se genera por escenario. |
| Estado de los experimentos | Etiqueta `reference` / `REFERENCE_INPUTS_UNVERIFIED` en lugar de `observed`. |
| Diseño y exportaciones | Panel para mostrar catálogo original, precio, vida útil, subventanas, políticas, trazas, escenarios, sensibilidad e informes CSV/JSON. |

## 3. Diseño experimental tomado del PDF

- **15 productos**: 6 panadería, 5 embutidos y 4 lácteos.
- **3 escalas** de demanda diaria de referencia: pequeña 5, mediana 15, grande 30 unidades por producto (supuestos de experimento).
- **9 escenarios**: rotación `k = {0.70, 1, 1.30}` × stock `s = {0.75, 1, 1.50}`. `R_teórica = s/k`; `R_efectiva = S0 / (k × B)`.
- **2 modelos** de demanda sensibles a precio y frescura: B isoelástico y C logit, calibrados con la misma elasticidad inicial.
- **4 políticas:** `P0 = 0 %`, `P1 = 20 %`, `P2 = 10/20/30 %` (o `10/30 %` con dos bloques) y `P3 = 0..30 %` en saltos de 5 puntos y reoptimización al iniciar cada subventana.
- **3 240 evaluaciones deterministas** = 15 × 3 × 9 × 2 × 4, antes de repeticiones.
- **Indicador principal:** `L (S/) = S0 × precio_regular − suma(ventas_diarias × precio_con_descuento)`; no es merma contable. También se reportan porcentaje, ventas, inventario y recaudación.
- **Monte Carlo opcional:** Poisson o binomial negativa, uniformes comunes entre políticas, contrastes pareados e IC del 95 %. El diseño prevé 1000 réplicas iniciales y más solo cuando sea necesario.

**Supuestos:** un lote homogéneo sin reposición; sin donaciones; costo adicional de retiro S/ 0; adquisición constante entre escenarios y excluida de la función objetivo; sin ventas después del vencimiento.

## 4. Ejecución por consola

```bash
# 1 producto, E5, escala mediana; genera HTML de ejemplo, tablas, graficos
python run.py --mode demo --replicas 1000

# 15 x 3 x 9 x 2 x 4 = 3240 evaluaciones sobre la matriz recibida
python run.py --mode deterministic --output results/matriz_referencia

# Prueba estocástica acotada para evitar procesos excesivos
python run.py --mode stochastic --max-cases 1 --model B --distribution poisson --replicas 1000

# Sensibilidad a frescura, elasticidad, redondeo y pesos; B/C cruzados
python run.py --mode sensitivity

# Ejecutar controles y pruebas del modelo
python -m pytest -q
```

Los archivos creados incluyen CSV, figuras PNG/SVG y `reproducibilidad.json` con la huella SHA-256 del Excel, semilla y dependencias. La exportación Parquet funciona cuando está instalado `pyarrow`.

También puedes abrir **`Vista_previa_SQV.html`** con doble clic, sin instalar Python,
para explorar interactivamente los **resultados deterministas ya calculados**.
Es un visor autónomo, no ejecuta simulaciones nuevas. Para actualizarlo después
de cambiar la matriz y volver a ejecutar el factorial:

```bash
python scripts/build_offline_preview.py
```

## 5. Qué validar antes de usarlo como resultado científico

1. Confirmar **vida útil** de los 15 productos frente a etiqueta/ficha; la hoja `Presentacion` declara este punto pendiente pese a que `Matriz_15` muestra cifras de prueba.
2. Revisar la categoría de los dos kekes incluidos en **Lácteos**, pues altera el anclaje de elasticidad.
3. Verificar fuentes/fecha de los precios de cada presentación y diferencias entre productos.
4. Contar con demanda/stock y costos reales si se desea estimar efectos comerciales o rentabilidad; las capturas de la hoja `Presentacion` son fotografías puntuales, no ventas mensuales.
5. Calibrar `lambda`, `beta`, `theta`, pesos y elasticidades por SKU; realizar sensibilidad y convergencia antes de conclusiones.

Leer **`docs/ADAPTACION_MATRIZ_Y_PDF.md`** para trazabilidad y supuestos y **`docs/MANUAL_TECNICO.md`** para las ecuaciones y reglas internas.

## 6. Estructura

```text
app.py, run.py                 panel Streamlit y linea de comandos
src/sqv/                      motor y validaciones
configs/                      parametros del experimento
data/Matriz_15_productos_fuente.xlsx        Excel recibido, sin cambios
data/matriz_sintetica_15.xlsx               demo antigua (separada)
docs/Resumen_proyecto_SQV_2_paginas.pdf    PDF recibido
docs/ADAPTACION_MATRIZ_Y_PDF.md            trazabilidad de cambios
results/matriz_referencia/                 resultados sobre el Excel recibido
results/                                  archivos previos etiquetados como demo
figures/                                  graficos previos y actualizados
Vista_previa_SQV.html                    visor determinista offline, interactivo
tests/                                    pruebas unitarias e integracion
```
