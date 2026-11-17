# Desplegar SQV en Render

La configuración publica el panel Streamlit completo, con su fuente única: `Matriz_15_productos_actualizada (1) (1).xlsx`, hoja `Matriz_15`.

## Despliegue con Blueprint

1. Descomprime `SQV_Render.zip` en una carpeta nueva.
2. Sube su contenido a un repositorio de GitHub o GitLab. `render.yaml` y `app.py` deben quedar en la raíz del repositorio, junto con el Excel original, `src/`, `assets/`, `configs/`, `scripts/` y `.streamlit/`. Incluye también `.python-version`.
3. En Render, selecciona **New → Blueprint** y conecta ese repositorio. Render admite Blueprints en la raíz con el nombre `render.yaml`. [Referencia oficial](https://render.com/docs/blueprint-spec).
4. Revisa el servicio `sqv-laboratorio` y el plan antes de confirmar. La configuración selecciona **1 CPU / 2 GB**, identificador `1c-2g`, **de pago**. La memoria está destinada a las corridas de Monte Carlo; no constituye una garantía para cualquier número de sesiones concurrentes. Puedes modificar `plan` en `render.yaml`. [Planes admitidos en Blueprints](https://render.com/docs/blueprint-spec#plan).
5. Confirma el despliegue. El build instala las dependencias y comprueba la matriz. En los registros debe aparecer `Render OK: 15 productos del Excel original, 405 casos...`.
6. Abre la URL que asigne Render. Selecciona un caso y verifica que cambian sus indicadores. Para demanda aleatoria, pulsa **Aplicar cambios y ejecutar Monte Carlo**.

El archivo no fija una URL de repositorio ni una rama: Render usa el repositorio y la rama del Blueprint. Los commits posteriores activan nuevos despliegues. Para desactivar ese comportamiento, cambia `autoDeployTrigger` a `"off"`.

## Configuración manual alternativa

Si creas **New → Web Service** en lugar de un Blueprint, introduce estos valores:

| Campo | Valor |
| --- | --- |
| Runtime / Language | Python |
| Root Directory | Vacío, si `app.py` está en la raíz del repositorio |
| Build Command | `bash scripts/render-build.sh` |
| Start Command | `python -m streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT --server.headless=true --server.fileWatcherType=none --browser.gatherUsageStats=false` |
| Health Check Path | `/_stcore/health` |
| Instances | 1 |
| Compute | 1 CPU / 2 GB, o los recursos que hayas decidido contratar |

Añade estas variables de entorno en la creación manual; el Blueprint ya las incluye:

```text
PYTHONUNBUFFERED=1
MPLCONFIGDIR=/tmp/sqv-matplotlib
MPLBACKEND=Agg
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
```

`.python-version` selecciona Python 3.12 y Render resuelve el parche más reciente de esa serie. Las dependencias directas están fijadas en `requirements-render.txt` según el entorno local verificado. Las dependencias transitivas las resuelve pip. No hace falta establecer `PYTHON_VERSION`; si el servicio ya la tiene, elimínala o asegúrate de que indique una versión completa de Python 3.12, ya que esa variable tiene prioridad sobre el archivo. [Versión de Python en Render](https://render.com/docs/python-version).

Render proporciona `PORT`; el proceso escucha en `0.0.0.0`. No configures un puerto fijo en el panel. El servicio debe ser **Web Service**, ya que Streamlit necesita ejecutar Python e intercambiar datos con el navegador. [Puertos y servicios web](https://render.com/docs/web-services#port-binding).

## Archivos y sesiones

- Conserva exactamente el nombre del Excel original; el build falla si falta o si `configs/base.yaml` apunta a otra fuente.
- El paquete usa una lista explícita de archivos e incluye el Excel y el código. Excluye entornos virtuales, credenciales, cachés y las corridas grandes de `results/`.
- El panel calcula los resultados al solicitarlo; no necesita subir los CSV de experimentos anteriores.
- Los resultados de cada usuario viven en la memoria de su sesión. Reiniciar o redesplegar el proceso interrumpe esas sesiones. Descarga los CSV o el ZIP desde **08 Exportación** para conservar una corrida. Esta configuración no incorpora una base de datos ni archivo persistente de sesiones.
- Se mantiene una instancia. Para distribuir usuarios entre varias instancias hay que diseñar el almacenamiento y el manejo de sesiones antes de escalar.

## Comprobación y empaquetado local

Con las dependencias instaladas:

```bash
python scripts/check_render.py
python scripts/package_render.py
```

El primer comando comprueba los archivos, los 15 productos, los 405 casos y una corrida de las cuatro políticas con ambos modelos. El segundo crea `SQV_Render.zip` y un manifiesto de integridad dentro del ZIP. No crea un servicio ni realiza un despliegue remoto.

La comprobación HTTP de Render utiliza `/_stcore/health`; ese endpoint comprueba el proceso Streamlit. La revisión del Excel y del motor se realiza separadamente durante el build. [Health checks en Render](https://render.com/docs/health-checks).

La preparación se verificó descomprimiendo el ZIP en una carpeta independiente: pasó la revisión del Excel y el panel cargó los 15 productos y cambió de escenario mediante Streamlit AppTest. También se comprobaron las huellas de todos los archivos del paquete y la coincidencia de las dependencias fijadas con el entorno instalado. La prueba HTTP local quedó bloqueada por las restricciones de sockets del entorno; el endpoint HTTP y la instalación limpia de dependencias deben confirmarse durante el despliegue en Render. No se ha creado ni publicado un servicio remoto.
