"""Scientific tables, chart exports and version/seed auditing."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import html
import os
import json
import platform
import sys
import importlib.metadata as md
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .experiments import summarize_results,paired_comparisons,winning_policy_frequency
from . import __version__


def save_frame(frame: pd.DataFrame,path: Path, parquet=True) -> dict:
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(path,index=False,encoding='utf-8-sig',float_format='%.17g')
    out={'csv':str(path)}
    if parquet:
        try:
            other=path.with_suffix('.parquet')
            frame.to_parquet(other,index=False)
            out['parquet']=str(other)
        except ImportError:
            out['parquet']='NO GENERADO: instalar pyarrow'
    return out


def write_tables(df: pd.DataFrame,directory: Path,prefix: str):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    outputs={'replicas':save_frame(df,directory/f'{prefix}_evaluaciones.csv')}
    summary=summarize_results(df)
    outputs['summary']=save_frame(summary,directory/f'{prefix}_resumen.csv')
    comparison=paired_comparisons(df)
    if not comparison.empty:
        outputs['pairs']=save_frame(comparison,directory/f'{prefix}_comparaciones_pareadas.csv')
    win=winning_policy_frequency(df)
    outputs['wins']=save_frame(win,directory/f'{prefix}_politica_ganadora.csv')
    return outputs


def make_figures(df: pd.DataFrame, directory: Path, prefix='sqv') -> list[str]:
    """Create 300-dpi publication-ready PNG and vector SVG plots."""
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    if df.empty: return []
    synthetic=df.source.eq('synthetic').any()
    note='DATOS SINTÉTICOS - SOLO DEMOSTRACION' if synthetic else 'MATRIZ A VALIDAR - NO ES EVIDENCIA CAUSAL'
    figures=[]
    cols=['#b5afc4','#b8ce75','#9d8ee1','#6852e8']
    # Average loss by policy; disaggregated by model.
    pivot=(df.groupby(['model','policy']).loss_soles.mean()
           .unstack('policy').reindex(columns=['P0','P1','P2','P3']))
    fig,ax=plt.subplots(figsize=(9,5.2))
    pivot.plot(kind='bar',ax=ax,color=cols,width=.74,rot=0)
    ax.set(xlabel='Modelo de demanda',ylabel='Pérdida potencial media (S/)',
           title='Comparación de políticas por especificación de demanda')
    ax.grid(axis='y',alpha=.22)
    ax.set_ylim(0,ax.get_ylim()[1]*1.20)
    ax.legend(title='Política',ncol=4,loc='upper center',frameon=False)
    fig.text(.5,.02,note,ha='center',fontsize=9,color='#a94b26')
    fig.tight_layout(rect=(0,.045,1,1))
    for suffix in ('png','svg'):
        path=directory/f'{prefix}_comparacion_modelos.{suffix}'
        fig.savefig(path,dpi=300,bbox_inches='tight')
        figures.append(str(path))
    plt.close(fig)
    # Absolute R on horizontal axis, show a scatter by policy.
    aggregate=df.groupby(['scenario','policy','r_target'],as_index=False).loss_relative.mean()
    fig,ax=plt.subplots(figsize=(9,5.2))
    for j,pol in enumerate(('P0','P1','P2','P3')):
        group=aggregate[aggregate.policy==pol].sort_values('r_target')
        ax.plot(group.r_target,100*group.loss_relative,marker='o',label=pol,color=cols[j])
    ax.set(xlabel='Presion relativa teorica R = s/k',ylabel='Pérdida relativa media (%)',
           title='Pérdida potencial según presión de inventario')
    ax.grid(alpha=.22); ax.legend()
    fig.text(.5,.02,note,ha='center',fontsize=9,color='#a94b26')
    fig.tight_layout(rect=(0,.045,1,1))
    for suffix in ('png','svg'):
        path=directory/f'{prefix}_presion_inventario.{suffix}'
        fig.savefig(path,dpi=300,bbox_inches='tight')
        figures.append(str(path))
    plt.close(fig)
    # CI chart of paired differences for stochastic runs if available.
    pairs=paired_comparisons(df)
    if not pairs.empty:
        first=pairs.iloc[0]
        subset=pairs[(pairs.product_id==first.product_id)&(pairs.scenario==first.scenario)&
                     (pairs.scale==first.scale)&(pairs.model==first.model)&
                     (pairs.distribution==first.distribution)].set_index('comparison')
        fig,ax=plt.subplots(figsize=(8.7,4.5))
        ax.errorbar(subset.index,subset['mean'],
                    yerr=[subset['mean']-subset['ci_low'],subset['ci_high']-subset['mean']],
                    fmt='o',capsize=4,color=cols[0],linewidth=1.8)
        ax.axhline(0,color='#333',linewidth=1,linestyle='--')
        ax.set(xlabel='Comparacion pareada',ylabel='Diferencia media de pérdida (S/)',
               title=f'IC95 pareados | {first.product_id} / {first.scenario} / {first.model}')
        fig.text(.5,.01,note+' | Un caso, una distribucion; NO intervalo agregado.',
                 ha='center',fontsize=8,color='#a94b26')
        fig.tight_layout(rect=(0,.065,1,1))
        for suffix in ('png','svg'):
            path=directory/f'{prefix}_pares_exploratorios.{suffix}'
            fig.savefig(path,dpi=300,bbox_inches='tight');figures.append(str(path))
        plt.close(fig)
    return figures


def checksum(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        while block:=f.read(1024*1024): h.update(block)
    return h.hexdigest()


def manifest(directory:Path, *, input_path:Path,mode:str,seed:int,
             parameters:dict,run_count:int, source_files: list[Path] | None=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    versions={}
    for pkg in ('numpy','pandas','scipy','matplotlib','pytest','pyarrow','streamlit'):
        try: versions[pkg]=md.version(pkg)
        except md.PackageNotFoundError: versions[pkg]='NO INSTALADO'
    hashes={str(Path(input_path).name):checksum(input_path)}
    for p in source_files or []:
        hashes[str(p)]=checksum(p)
    record={'project_version':__version__,'created_utc':datetime.now(timezone.utc).isoformat(),
            'python':platform.python_version(),'platform':platform.platform(),
            'mode':mode,'seed':seed,'parameters':parameters,'evaluations':run_count,
            'dependencies':versions,'sha256_files':hashes,
            'epistemic_status':'SYNTHETIC_DEMO_NOT_OBSERVED' if 'sintetic' in str(input_path).lower()
                                or 'synthetic' in str(input_path).lower() else 'REQUIRES_SOURCE_VALIDATION'}
    path=directory/'reproducibilidad.json'
    path.write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8')
    return path


def freeze_inputs(products, directory, config):
    """Freeze normalized imports so later analysis never needs to reread Excel."""
    from dataclasses import asdict
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    normalized = directory/'productos_normalizados.json'
    normalized.write_text(json.dumps([asdict(p) for p in products], indent=2, ensure_ascii=False), encoding='utf-8')
    frozen = directory/'configuracion_congelada.json'
    frozen.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
    return [normalized, frozen]


def static_html_report(df: pd.DataFrame,directory:Path,figures:list[str],title:str='SQV | Informe de simulacion') -> Path:
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    summary=(df.groupby('policy').agg(perdida_soles=('loss_soles','mean'),
            ingresos_soles=('revenue_soles','mean'),remanente=('remaining','mean')).round(2))
    aggregate=summary.reset_index().to_html(index=False,classes='result-table',border=0)
    items='\n'.join(f'<figure><img src="{html.escape(os.path.relpath(f, start=directory))}" alt="grafico SQV"></figure>'
                    for f in figures if f.endswith('.png'))
    banner='DATOS SINTÉTICOS - NO SON RESULTADOS EMPIRICOS' if df.source.eq('synthetic').any() else 'DATOS DE ENTRADA PENDIENTES DE VALIDACION'
    page=f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font:16px/1.6 system-ui,-apple-system,sans-serif;margin:0;background:#f7f7fa;color:#242333}}header{{background:#242332;color:white;padding:44px max(5vw,24px)}}main{{max-width:1050px;margin:32px auto;padding:0 20px}}h1{{font-size:2.5rem;letter-spacing:-.05em;margin:0}}h2{{color:#6852e8;margin-top:36px}}.banner{{color:#8c4300;background:#fff4dd;padding:14px 20px;border-left:5px solid #b8ce75;margin:20px 0}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{padding:14px 16px;text-align:left;border-bottom:1px solid #e6edf3}}th{{background:#eee9fb;color:#6852b8}}figure{{background:white;padding:15px;margin:22px 0;border-radius:12px;box-shadow:0 4px 18px #14344810}}img{{width:100%;max-width:100%;display:block}}footer{{margin:35px 0;color:#596c7f}}</style></head>
<body><header><h1>{html.escape(title)}</h1><p>Prototipo computacional de optimizacion de descuentos | v1.2</p></header>
<main><div class="banner"><strong>{banner}</strong></div><p>La perdida potencial de ingresos se calcula como valor inicial del inventario a precio regular menos ingresos realizados. No equivale a perdidas contables observadas.</p>
<h2>Comparacion por politica</h2>{aggregate}<h2>Figuras</h2>{items}<h2>Nota cientifica</h2><p>Los resultados de simulacion no demuestran mejora comercial causal. La matriz real de productos, los parametros de demanda y las pruebas de robustez deben validarse antes de presentar evidencia definitiva.</p><footer>Motor SQV | Simulacion trazable y reproducible</footer></main></body></html>'''
    output=directory/'reporte_demo.html'
    output.write_text(page,encoding='utf-8')
    return output


def robustness_figures(sensitivity: pd.DataFrame | None,
                       cross: pd.DataFrame | None, directory: Path) -> list[str]:
    """Figures for deterministic parameter and B/C misspecification robustness."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    outputs=[]
    if sensitivity is not None and not sensitivity.empty:
        pivot=(sensitivity[sensitivity.policy=='P3']
               .groupby(['sensitivity_variant','model']).loss_soles.mean().unstack())
        fig,ax=plt.subplots(figsize=(11,5.7))
        pivot.plot(kind='bar',ax=ax,rot=28,color=['#6852e8','#b8ce75'])
        ax.set(xlabel='Variacion (un factor a la vez)',ylabel='Perdida media P3 (S/)',
               title='Robustez de la perdida potencial ante supuestos experimentales')
        ax.grid(axis='y',alpha=.2)
        ax.legend(title='Modelo de demanda')
        fig.text(.5,.01,'DATOS SINTETICOS - SOLO DEMO' if
                 sensitivity.source.eq('synthetic').any() else
                 'MATRIZ DE REFERENCIA - PENDIENTE DE VALIDACION',
                 ha='center',fontsize=9,color='#a94b26')
        fig.tight_layout(rect=(0,.04,1,1))
        for suffix in ('png','svg'):
            name=directory/f'sensibilidad_P3.{suffix}'
            fig.savefig(name,dpi=300,bbox_inches='tight');outputs.append(str(name))
        plt.close(fig)
    if cross is not None and not cross.empty:
        pivot=(cross[cross.policy=='P3'].groupby(['model','decision_model']).loss_soles.mean()
               .unstack('decision_model').reindex(index=['B','C'],columns=['B','C']))
        fig,ax=plt.subplots(figsize=(7.8,5.6))
        heat=ax.imshow(pivot.to_numpy(),cmap='Purples')
        fig.colorbar(heat,ax=ax,label='Pérdida potencial media (S/)')
        ax.set_xticks([0,1],labels=['B · isoelastico','C · logit'])
        ax.set_yticks([0,1],labels=['B · isoelastico','C · logit'])
        ax.set(xlabel='Modelo utilizado para decidir P3',ylabel='Modelo generador de demanda',
               title='Prueba de especificacion cruzada B ↔ C')
        for (i,j),val in np.ndenumerate(pivot.to_numpy()):
            ax.text(j,i,f'S/ {val:.2f}',ha='center',va='center',fontsize=11,
                    color='white' if val>np.nanmean(pivot.to_numpy()) else '#19354d')
        fig.text(.5,.02,('MATRIZ SINTÉTICA' if cross.source.eq('synthetic').any() else 'MATRIZ REFERENCIAL')+' · Escenarios equiponderados · No evidencia observada',
                 ha='center',fontsize=9,color='#a94b26')
        fig.tight_layout(rect=(0,.04,1,1))
        for suffix in ('png','svg'):
            name=directory/f'calibracion_cruzada_B_C.{suffix}'
            fig.savefig(name,dpi=300,bbox_inches='tight');outputs.append(str(name))
        plt.close(fig)
    return outputs


def dispersion_figures(df:pd.DataFrame,directory:Path) -> list[str]:
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if df.empty: return []
    pivot=df.groupby(['theta_experimental','policy']).loss_soles.mean().unstack('policy')
    fig,ax=plt.subplots(figsize=(8.3,5.1))
    pivot.plot(ax=ax,marker='o',color=['#b5afc4','#b8ce75','#9d8ee1','#6852e8'])
    ax.set(xlabel='Parametro de dispersion θ',ylabel='Pérdida potencial media (S/)',
           title='Sensibilidad a la sobredispersion binomial negativa')
    ax.grid(alpha=.2)
    fig.text(.5,.015,'DEMO CON PARAMETROS EXPERIMENTALES - NO CALIBRADOS',
             ha='center',fontsize=9,color='#a94b26')
    fig.tight_layout(rect=(0,.045,1,1))
    files=[]
    for suffix in ('png','svg'):
        path=directory/f'dispersion_theta.{suffix}'
        fig.savefig(path,dpi=300,bbox_inches='tight');files.append(str(path))
    plt.close(fig)
    return files


def convergence_figures(logs: pd.DataFrame, directory:Path) -> list[str]:
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if logs.empty: return []
    fig,ax=plt.subplots(figsize=(8.5,5.1))
    for key,part in logs.groupby(['product_id','scenario','scale','model','distribution'],sort=False):
        ax.plot(part.replicas,part.max_ci_halfwidth_soles,marker='o',label='/'.join(map(str,key)))
    ax.set(xlabel='Réplicas acumuladas',ylabel='Máxima semiamplitud IC95 (S/)',
           title='Convergencia de la incertidumbre por etapa')
    ax.grid(alpha=.2)
    ax.legend(loc='best',fontsize=8)
    fig.text(.5,.015,'No interpretar convergencia como validez externa o causalidad',
             ha='center',color='#a94b26',fontsize=9)
    fig.tight_layout(rect=(0,.045,1,1))
    result=[]
    for suffix in ('png','svg'):
        p=directory/f'convergencia_ic95.{suffix}'
        fig.savefig(p,dpi=300,bbox_inches='tight');result.append(str(p))
    plt.close(fig)
    return result
