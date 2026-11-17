# Manual de usuario - Interfaz SQV

## Instalar y abrir

1. Instalar Python >=3.11.
2. Ejecutar `python -m pip install -r requirements.txt` en la carpeta principal.
3. Ejecutar `streamlit run app.py`.
4. Abrir la URL local que muestre Streamlit.
5. La app usa **únicamente la matriz de 15 productos proporcionada**, en
`Matriz_15_productos_actualizada (1) (1).xlsx`, hoja `Matriz_15`. No permite alternar a demos ni subir otra matriz.

La demanda y el inventario experimental se generan según la guía. La clasificacion de dos kekes bajo Lacteos
se mantiene segun la especificacion, pero esta marcada para revision de
sensibilidad de elasticidad.

## Descripcion de los ocho paneles

| Vista | Funciones |
| --- | --- |
| 01 Configuracion | Parametros de producto, k, s, R, B, lambda, frescura |
| 02 Simulacion | Factorial determinista / Monte Carlo del caso |
| 03 Inventario | Tabla y curva de venta/stock diaria |
| 04 Optimizacion P3 | Decisiones por subventana, descuentos y trayectoria |
| 05 Resultados | Ingresos, remanente, perdida potencial y contraste P3-P0 |
| 06 Estadistica | Media, desviacion, IC95, diferencias pareadas, convergencia |
| 07 Sensibilidad | beta, alpha, demanda B/C y theta binomial negativa |
| 08 Exportacion | Descargas CSV/JSON, detalladas y resumidas |

## Un ejemplo reproducible

Seleccionar `SQV001 · Pan de molde blanco PyC — 480 g`, escala `mediana`, escenario `E5`,
modelo `B`. En **05 Resultados** ver P0-P3 para una corrida determinista.
En la barra lateral, configura **03 · Monte Carlo** con 1.000 réplicas y Poisson;
pulsa **Aplicar cambios y ejecutar Monte Carlo**. Este botón cambia la vista a Monte Carlo.
Las pérdidas medias aparecen arriba y en **05 Resultados**; en **06 Estadística** se muestran IC95 y diferencias P3-P0/P1/P2.

Cambiar producto, escala, escenario o modelo actualiza inmediatamente el cálculo determinista.
Cambiar distribución, réplicas, semilla o el caso deja Monte Carlo **pendiente de actualizar** hasta pulsar de nuevo el botón. Así no se presentan resultados anteriores como si correspondieran a la configuración nueva.

**03 Inventario** y **04 Optimización P3** muestran trayectorias deterministas y lo indican en sus títulos. El precio regular y la vida útil no cambian al cambiar de escenario: provienen del mismo producto del Excel. Dos modelos pueden dar la misma venta al redondear a unidades enteras.

Si abres `Vista_previa_SQV.html` con doble clic, estás en el visor de resultados deterministas. Para Monte Carlo debes abrir el panel Streamlit mediante el iniciador de tu sistema.

La semilla predeterminada 20261114 hace reproducibles los experimentos en la
misma version de Python/dependencias. Si el criterio de IC no converge, no
presentar diferencias como estadisticamente resueltas.

## Formato de la matriz utilizada

- Hoja `Matriz_15`, exactamente 15 productos. Se detectan encabezados incluso en
la fila 4; el campo ID es opcional (SQV001...SQV015 segun el orden del Excel).
- Categorias 6 Panaderia / 5 Embutidos / 4 Lacteos.
- Ventanas unicamente 2,3,10,15 y bloques asociados. Se aceptan `3 dias` y
  `4 / 3 / 3 días`; `1 días` se interpreta como bloques diarios, no uno solo.
- Precio p0, vida util, ventana y presentacion fieles a la fuente.
- Documentar procedencia y fecha de precios; validar elasticidades por categoria.
- Marcar `source=observed` SOLO si proviene de mediciones reales.
- Si tiene datos faltantes, el importador informa el campo y no avanza.

## Uso sin interfaz

- `python run.py --mode demo`: genera reporte HTML y tablas con matriz referencial (default).
- `python run.py --mode deterministic`: 3240 evaluaciones en CSV.
- `python run.py --mode stochastic --max-cases 1 ...`: Monte Carlo acotado.
- `python run.py --mode adaptive --max-cases 1 ...`: IC95 secuencial.
- `python -m pytest -q`: tests.

La carpeta `results/` contiene los registros; `figures/` los graficos.
Si instala pyarrow, tambien podra exportar Parquet. Ver `README.md`.
