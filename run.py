#!/usr/bin/env python3
"""Main CLI for reproducible SQV experiments.

Quick smoke: python run.py --mode demo
Full factorial: python run.py --mode deterministic
Matriz adjunta: python run.py --mode deterministic --input data/Matriz_15_productos_fuente.xlsx
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from sqv.load import load_products
from sqv.config import load_config
from sqv.scenarios import build_cases
from sqv.experiments import (run_deterministic,run_stochastic,run_adaptive,
                             deterministic_sensitivity,run_cross_calibration,stochastic_dispersion_sensitivity,stream_stochastic_to_disk,convergence_check)
from sqv.reports import write_tables,make_figures,static_html_report,manifest,save_frame,robustness_figures,dispersion_figures,convergence_figures,freeze_inputs
from sqv.model import FORMS
from sqv.engine import simulate,trace_records


def main(argv=None):
    preliminary=argparse.ArgumentParser(add_help=False)
    preliminary.add_argument('--config',default=str(ROOT/'configs/base.yaml'))
    pre,_=preliminary.parse_known_args(argv)
    config_path=Path(pre.config).resolve()
    config=load_config(config_path)
    experiment=config['experimento']
    parser=argparse.ArgumentParser(description='Motor cientifico SQV v1.2 | matriz de referencia incorporada')
    parser.add_argument('--config',default=str(config_path),help='Configuración YAML del experimento')
    parser.add_argument('--mode',choices=['demo','deterministic','stochastic','adaptive','sensitivity','dispersion'],default='demo')
    parser.add_argument('--input',default=str(ROOT/'data'/'Matriz_15_productos_fuente.xlsx'))
    parser.add_argument('--data-type',choices=['synthetic','observed','reference'],default=None)
    parser.add_argument('--output',default=None)
    parser.add_argument('--seed',type=int,default=20261114)
    parser.add_argument('--replicas',type=int,default=1000)
    parser.add_argument('--max-cases',type=int,default=None,
                        help='Limita casos, solo para ensayos; omitir para barrido total')
    parser.add_argument('--model',choices=['B','C','both'],default='both')
    parser.add_argument('--distribution',choices=['poisson','nbinom','both'],default='both')
    parser.add_argument('--theta',type=float,default=10.)
    parser.add_argument('--rounding',choices=['full','cents'],default='full')
    parser.add_argument('--scenario',default=None,help='Filtrar E1..E9')
    parser.add_argument('--scale',default=None,choices=['pequena','mediana','grande'])
    parser.add_argument('--product',default=None)
    parser.add_argument('--stages',default='1000,5000,10000,50000,100000')
    parser.add_argument('--theta-values',default='5,10,30',help='Valores de theta para --mode dispersion')
    parser.set_defaults(input=str(ROOT/config['fuente']['archivo']),
        seed=experiment['semilla'],theta=experiment['theta'],rounding=experiment['precio_redondeo'],
        stages=','.join(map(str,experiment['niveles_replicas'])))
    args=parser.parse_args(argv)
    input_path=Path(args.input).resolve()
    source=args.data_type or ('synthetic' if input_path.name.startswith('matriz_sintetica') else 'reference')
    products=load_products(input_path,source=source)
    products=[replace(p,beta=float(experiment['beta_central']),
                      alpha=float(experiment['alpha_por_categoria'][p.category])) for p in products]
    cases=build_cases(products,scales=experiment['lambda_por_escala'],
                      k_values=tuple(experiment['rotation_k']),s_values=tuple(experiment['stock_s']))
    if args.scenario: cases=[c for c in cases if c.scenario==args.scenario]
    if args.scale: cases=[c for c in cases if c.scale==args.scale]
    if args.product: cases=[c for c in cases if c.product.id==args.product]
    if not cases: parser.error('No hay casos para los filtros especificados')
    forms=FORMS if args.model=='both' else (args.model,)
    distr=('poisson','nbinom') if args.distribution=='both' else (args.distribution,)
    if args.mode=='demo':
        # E5/mediana first product: intentionally SMALL reproducibility demo.
        cases=[c for c in cases if c.product.id==products[0].id and c.scenario=='E5' and c.scale=='mediana']
        if not cases: parser.error('Demo requiere el primer producto en E5/mediana')
        output=Path(args.output or ROOT/('results/demo_sintetico' if source=='synthetic' else 'results/demo_matriz_referencia'))
    else:
        if args.max_cases:
            cases=cases[:args.max_cases]
        output=Path(args.output or ROOT/('results/matriz_referencia' if args.mode=='deterministic' and source=='reference' else f'results/{args.mode}'))
    output.mkdir(parents=True,exist_ok=True)
    if args.mode=='demo':
        deterministic=run_deterministic(cases,forms=forms,price_rounding=args.rounding)
        stochastic=run_stochastic(cases,forms=forms,distributions=distr,
                                 replicas=args.replicas,seed=args.seed,theta=args.theta,price_rounding=args.rounding)
        all_df=__import__('pandas').concat([deterministic,stochastic],ignore_index=True)
        write_tables(deterministic,output,'demo_deterministic')
        write_tables(stochastic,output,'demo_estocastico')
        tag='demo_sintetico' if source=='synthetic' else 'demo_matriz_referencia'
        figures=make_figures(deterministic,ROOT/'figures',tag)
        figures+=make_figures(stochastic,ROOT/'figures',tag+'_estocastico')
        static_html_report(deterministic,output,figures)
        trace_df=__import__('pandas').DataFrame([entry for case in cases for f in forms
                    for policy in ('P0','P1','P2','P3')
                    for entry in trace_records(simulate(case,policy,f,price_rounding=args.rounding))])
        save_frame(trace_df,output/'demo_trazabilidad_diaria.csv')
        df=all_df
        record_count=len(df)
        ok,_,_=convergence_check(stochastic)
        print(f'Demo ({source.upper()}): {len(deterministic)} deterministas + {len(stochastic)} estocasticas; convergencia={ok}')
    elif args.mode=='deterministic':
        df=run_deterministic(cases,forms=forms,price_rounding=args.rounding)
        record_count=len(df)
        write_tables(df,output,'base_determinista')
        figures=make_figures(df,ROOT/'figures','factorial_determinista' if source=='synthetic' else 'matriz_referencia')
        report=static_html_report(df,output,figures,title='SQV | Matriz referencial (15 productos)' if source=='reference' else 'SQV | Datos sinteticos')
        if source=='reference': report.rename(output/'reporte_matriz_referencia.html')
        print(f'Barrido determinista: {len(df)} evaluaciones de politica; casos={len(cases)}')
    elif args.mode=='stochastic':
        estimated=len(cases)*len(forms)*len(distr)*4*args.replicas
        if estimated>100000:
            info=stream_stochastic_to_disk(cases,output,forms=forms,distributions=distr,
                        replicas=args.replicas,seed=args.seed,theta=args.theta,
                        price_rounding=args.rounding)
            df=None
            record_count=info['count']
            print(f'BARRIDO ESTOCASTICO por lotes: {record_count} trayectorias, {len(cases)} casos; memoria acotada')
        else:
            df=run_stochastic(cases,forms=forms,distributions=distr,
                              replicas=args.replicas,seed=args.seed,theta=args.theta,
                              price_rounding=args.rounding)
            record_count=len(df)
            write_tables(df,output,'estocastico')
            print(f'BARRIDO ESTOCASTICO: {len(df)} trayectorias, {args.replicas} replicas/configuracion')
    elif args.mode=='adaptive':
        stages=tuple(int(v.strip()) for v in args.stages.split(','))
        if len(distr)!=1:
            parser.error('--mode adaptive requiere --distribution poisson o nbinom')
        df,logs=run_adaptive(cases,forms=forms,distribution=distr[0],stages=stages,
                             seed=args.seed,theta=args.theta,price_rounding=args.rounding,
                             rel_tol=experiment['tolerancia_relativa_ic'],abs_tol=experiment['tolerancia_absoluta_diferencias_soles'])
        write_tables(df,output,'adaptativo')
        record_count=len(df)
        save_frame(logs,output/'convergencia_etapas.csv')
        convergence_figures(logs,ROOT/'figures')
        print(f'ADAPTATIVO: {len(df)} trayectorias; {logs.converged.sum()} etapas convergentes')
    elif args.mode=='dispersion':
        values=tuple(float(x.strip()) for x in args.theta_values.split(','))
        df=stochastic_dispersion_sensitivity(cases,theta_values=values,replicas=args.replicas,
                                             seed=args.seed,forms=forms,price_rounding=args.rounding)
        record_count=len(df)
        save_frame(df,output/'dispersion_nbinom.csv')
        dispersion_figures(df,ROOT/'figures')
        print(f'DISPERSION: {len(df)} trayectorias, theta={values}')
    else:
        df=deterministic_sensitivity(products,forms=forms)
        save_frame(df,output/'sensibilidad_completa.csv')
        cross=run_cross_calibration(cases,rounding=args.rounding)
        record_count=len(df)+len(cross)
        save_frame(cross,output/'calibracion_cruzada_B_C.csv')
        robustness_figures(df,cross,ROOT/'figures')
        print(f'SENSIBILIDAD: {len(df)} evaluaciones y {len(cross)} resultados cruzados B/C')
    settings={'model':args.model,'distribution':args.distribution,
              'replicas':args.replicas,'theta':args.theta,'rounding':args.rounding,
              'case_count':len(cases),'data_type':source,'inputs_are_reference_not_observed_sales':source=='reference','filters':{'product':args.product,
              'scenario':args.scenario,'scale':args.scale},'stages':args.stages}
    settings['experiment']=experiment
    settings['theta_values']=args.theta_values
    frozen=freeze_inputs(products,output,settings)
    code_files=sorted((ROOT/'src/sqv').glob('*.py'))+[ROOT/'run.py',ROOT/'app.py',config_path]
    out=manifest(output,input_path=input_path,mode=args.mode,seed=args.seed,
                 parameters=settings,run_count=record_count,source_files=code_files+frozen)
    print(f'Archivos en: {output}\nManifiesto: {out}')

if __name__=='__main__': main()
