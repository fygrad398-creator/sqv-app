"""Reproducible factorial experiments, Monte Carlo uncertainty and sensitivity."""
from __future__ import annotations
from dataclasses import replace
from collections import Counter
from typing import Callable, Iterable
import math
import numpy as np
import pandas as pd
from scipy.stats import t as student_t
from .model import Case, Product, FORMS, POLICIES
from .scenarios import build_cases
from .engine import simulate
from .stochastic import common_uniforms


def run_batch(config, seed=None):
    """Guide API: deterministic baseline, both adaptive distributions and logs.

    config is a YAML path. Persist large factorials via the CLI streaming mode;
    this convenience API returns all evaluations and convergence history.
    """
    from pathlib import Path
    from .config import load_config
    from .load import load_products
    config_path = Path(config).resolve()
    cfg = load_config(config_path)
    e = cfg['experimento']
    source = Path(cfg['fuente']['archivo'])
    if not source.is_absolute():
        source = config_path.parent.parent / source
    products = [replace(p, beta=float(e['beta_central']),
                        alpha=float(e['alpha_por_categoria'][p.category]))
                for p in load_products(source, source=cfg['fuente']['tipo'])]
    cases = build_cases(products)
    frames = [run_deterministic(cases, price_rounding=e['precio_redondeo'])]
    logs = []
    for distribution in e['distribuciones']:
        frame, history = run_adaptive(cases, forms=tuple(e['funciones']),
            distribution=distribution, stages=tuple(e['niveles_replicas']),
            seed=e['semilla'] if seed is None else seed, theta=e['theta'],
            rel_tol=e['tolerancia_relativa_ic'],
            abs_tol=e['tolerancia_absoluta_diferencias_soles'],
            price_rounding=e['precio_redondeo'])
        frames.append(frame)
        logs.append(history)
    return pd.concat(frames, ignore_index=True), pd.concat(logs, ignore_index=True)


def run_deterministic(cases: list[Case], *, forms=FORMS, policies=POLICIES,
                     price_rounding='full', progress: Callable|None=None) -> pd.DataFrame:
    rows, memo = [], {}
    total = len(cases)*len(forms)*len(policies)
    for i, case in enumerate(cases):
        for form in forms:
            for policy in policies:
                rows.append(simulate(case,policy,form,memo=memo,
                                     price_rounding=price_rounding).summary())
        if progress is not None:
            progress(i+1,len(cases))
    return pd.DataFrame(rows)


def run_stochastic(cases: list[Case], *, forms=FORMS, policies=POLICIES,
                   distributions=('poisson','nbinom'),replicas=1000,
                   seed=20261114,theta=10.,price_rounding='full',
                   case_index_offset: int=0, progress: Callable|None=None) -> pd.DataFrame:
    """CRN: same per-day U for all four policies, transformed by each policy's CDF."""
    if replicas < 2:
        raise ValueError('Se requieren al menos 2 replicas para IC95')
    rows=[]; memo={}
    for i, case in enumerate(cases):
        for form in forms:
            for distribution in distributions:
                # The form needs independent uniform streams; prevent accidental
                # coupling between models, but keep P0..P3 paired in a form.
                form_index=FORMS.index(form)
                if distribution not in ('poisson', 'nbinom'):
                    raise ValueError('Distribucion debe ser poisson o nbinom')
                d = 0 if distribution == 'poisson' else 1
                uniforms=common_uniforms(seed,case_index_offset+i,form_index*10+d,
                                         replicas,case.window)
                for rep in range(replicas):
                    shocks=uniforms[rep]
                    for policy in policies:
                        result=simulate(case,policy,form,shocks,distribution=distribution,
                                        theta=theta,memo=memo,price_rounding=price_rounding,
                                        seed=seed,replication=rep)
                        rows.append(result.summary())
        if progress is not None:
            progress(i+1,len(cases))
    return pd.DataFrame(rows)


def mean_ci95(values) -> dict:
    a = np.asarray(values,dtype=float)
    a = a[np.isfinite(a)]
    n=len(a)
    if not n: return {'n':0,'mean':float('nan'),'sd':float('nan'),
                      'ci_low':float('nan'),'ci_high':float('nan'),'halfwidth':float('nan')}
    mean=float(a.mean())
    if n<2: return {'n':n,'mean':mean,'sd':float('nan'),
                    'ci_low':float('nan'),'ci_high':float('nan'),'halfwidth':float('nan')}
    sd=float(a.std(ddof=1))
    half=float(student_t.ppf(.975,n-1)*sd/math.sqrt(n))
    return {'n':n,'mean':mean,'sd':sd,'ci_low':mean-half,'ci_high':mean+half,'halfwidth':half}


GROUP=['product_id','category','source','scenario','scale','model','distribution']

def summarize_results(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return pd.DataFrame()
    result=[]
    for key, group in df.groupby(GROUP+['policy'],dropna=False,sort=True):
        stats=mean_ci95(group.loss_soles)
        result.append({**dict(zip(GROUP+['policy'],key)),**stats,
                       'mean_revenue_soles':group.revenue_soles.mean(),
                       'mean_loss_relative':group.loss_relative.mean(),
                       'mean_remaining':group.remaining.mean(),
                       'r_effective':group.r_effective.iloc[0]})
    return pd.DataFrame(result)


def paired_comparisons(df: pd.DataFrame) -> pd.DataFrame:
    """IC95 for paired loss P3-minus-P0/P1/P2, NEGATIVE means P3 saved loss."""
    if df.empty or 'replication' not in df.columns or df.replication.isna().all():
        return pd.DataFrame()
    ans=[]
    for key, group in df.groupby(GROUP,dropna=False,sort=True):
        wide=group.pivot_table(index='replication',columns='policy',values='loss_soles',aggfunc='first')
        if 'P3' not in wide: continue
        for baseline in ('P0','P1','P2'):
            if baseline not in wide: continue
            delta=(wide['P3']-wide[baseline]).dropna().to_numpy()
            stats=mean_ci95(delta)
            ans.append({**dict(zip(GROUP,key)), 'comparison':f'P3-{baseline}',**stats,
                        'ci_includes_zero': bool(stats['ci_low']<=0<=stats['ci_high'])})
    return pd.DataFrame(ans)


def winning_policy_frequency(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return pd.DataFrame()
    index=GROUP + (['replication'] if 'replication' in df and df.replication.notna().any() else [])
    # Sort once instead of materializing a Python dict for every replication.
    # A stable policy rank keeps the P0/P1/P2/P3 tie convention.
    candidates=df[index+['policy','loss_soles']].copy()
    candidates['_policy_rank']=candidates.policy.map({p:i for i,p in enumerate(POLICIES)})
    winners=(candidates.sort_values(['loss_soles','_policy_rank'],kind='stable')
             .drop_duplicates(index).rename(columns={'policy':'winner'}))
    return (winners.groupby(GROUP+['winner'],dropna=False).size()
            .rename('wins').reset_index()
            .assign(n=lambda x:x.groupby(GROUP,dropna=False).wins.transform('sum'))
            .assign(frequency=lambda x:x.wins/x.n))


def convergence_check(df: pd.DataFrame, *, rel_tol=.02,abs_tol=.05):
    """Check all policy loss means and all paired differences with 95% CI.

    Policy means use relative precision; paired differences near zero use the
    declared absolute operational tolerance. Wider intervals need another stage.
    """
    summary=summarize_results(df)
    comparisons=paired_comparisons(df)
    checks=[]
    for _, row in summary.iterrows():
        tol=rel_tol*abs(row['mean'])
        checks.append(bool(row['halfwidth']<=tol))
    for _, row in comparisons.iterrows():
        near=abs(row['mean'])<=abs_tol
        tol=abs_tol if near else rel_tol*abs(row['mean'])
        checks.append(bool(row['halfwidth']<=tol))
    return bool(checks) and all(checks),summary,comparisons


def run_adaptive(cases: list[Case], *, forms=('B',), distribution='poisson',
                 stages=(1000,5000,10000,50000,100000),seed=20261114,
                 theta=10.,rel_tol=.02,abs_tol=.05,progress=None,
                 price_rounding='full') -> tuple[pd.DataFrame,pd.DataFrame]:
    """Run stagewise Monte Carlo per configuration; retain CRN and stage history.

    Computationally expensive by design. Uses independent deterministic
    substreams by original case index, model, distribution and seed.
    """
    if not stages or any(not isinstance(n, int) or n < 2 for n in stages) or any(
            b <= a for a, b in zip(stages, stages[1:])):
        raise ValueError('Etapas deben ser enteros crecientes de al menos 2 replicas')
    if distribution not in ('poisson', 'nbinom'):
        raise ValueError('Distribucion debe ser poisson o nbinom')
    if not (math.isfinite(rel_tol) and rel_tol > 0 and math.isfinite(abs_tol) and abs_tol > 0):
        raise ValueError('Tolerancias deben ser finitas y positivas')
    all_results=[]; logs=[]
    from .model import FORMS
    for ci,case in enumerate(cases):
        for form in forms:
            d_index=0 if distribution=='poisson' else 1
            uniforms=common_uniforms(seed,ci,FORMS.index(form)*10+d_index,max(stages),case.window)
            completed=0; memo={}; rows=[]
            for end in stages:
                if end<=completed or end>max(stages): raise ValueError('Etapas no crecientes')
                for rep in range(completed,end):
                    for policy in POLICIES:
                        rows.append(simulate(case,policy,form,uniforms[rep],distribution=distribution,
                                             theta=theta,memo=memo,seed=seed,replication=rep,
                                             price_rounding=price_rounding).summary())
                completed=end
                frame=pd.DataFrame(rows)
                good,summ,pairs=convergence_check(frame,rel_tol=rel_tol,abs_tol=abs_tol)
                logs.append({'product_id':case.product.id,'scenario':case.scenario,'scale':case.scale,
                             'model':form,'distribution':distribution,'replicas':end,
                             'converged':good,'max_ci_halfwidth_soles':max(summ.halfwidth.max(),
                                pairs.halfwidth.max() if not pairs.empty else 0.),
                             'relative_tolerance':rel_tol,'absolute_tolerance_soles':abs_tol,
                             'price_rounding':price_rounding,
                             'status':'converged' if good else ('limit_reached' if end == stages[-1] else 'continue')})
                if progress: progress(case,form,end,good)
                if good: break
            all_results.extend(rows)
    return pd.DataFrame(all_results),pd.DataFrame(logs)


def deterministic_sensitivity(products: list[Product], *,
            beta_values=(1.,2.,5.),alpha_multipliers=(.8,1.,1.2),
            rounding=('full','cents'),weight_modes=('uniform','heterogeneous'),
            forms=FORMS) -> pd.DataFrame:
    """One-factor-at-a-time tests for all cases; explicit synthetic status is kept."""
    records=[]
    variants=[]
    variants.extend((f'beta_{b:g}',[replace(p,beta=b) for p in products],'full') for b in beta_values)
    variants.extend((f'alpha_x{m:g}',[replace(p,alpha=p.alpha*m) for p in products],'full') for m in alpha_multipliers if m!=1)
    variants.extend((f'rounding_{r}',products,r) for r in rounding if r!='full')
    variants.append(('weights_uniform',[replace(p,weight=1.) for p in products],'full'))
    variants.append(('keke_alpha_panaderia',
                     [replace(p, alpha=.81) if p.sensitivity_flag else p for p in products], 'full'))
    if 'heterogeneous' in weight_modes:
        weights=np.linspace(.75,1.25,len(products))
        variants.append(('weights_heterogeneous',
                         [replace(p,weight=float(w)) for p,w in zip(products,weights)],'full'))
    for name,ps,mode in variants:
        cases=build_cases(ps)
        df=run_deterministic(cases,forms=forms,price_rounding=mode)
        df['sensitivity_variant']=name
        records.append(df)
    return pd.concat(records,ignore_index=True)


def run_cross_calibration(cases: list[Case], *, policies=('P3',),rounding='full') -> pd.DataFrame:
    """Cross-model robustness: generate demand with B/C, optimize with B/C.

    Off-diagonal B/C results are the scientifically relevant misspecification
    test. This deterministic routine keeps stock and scenario identical.
    """
    rows=[];memo={}
    for case in cases:
        for true_form in ('B','C'):
            for decision_form in ('B','C'):
                for policy in policies:
                    x=simulate(case,policy,true_form,decision_form=decision_form,
                               memo=memo,price_rounding=rounding)
                    row=x.summary()
                    row['calibration_type']='matched' if true_form==decision_form else 'cross_model'
                    rows.append(row)
    return pd.DataFrame(rows)


def stochastic_dispersion_sensitivity(cases: list[Case], *, theta_values=(5.,10.,30.),
                    replicas=1000,seed=20261114,forms=('B',),price_rounding='full') -> pd.DataFrame:
    """Negative-binomial overdispersion robustness under common uniforms."""
    frames=[]
    for theta in theta_values:
        frame=run_stochastic(cases,forms=forms,distributions=('nbinom',),
                             replicas=replicas,theta=theta,seed=seed,price_rounding=price_rounding)
        frame['theta_experimental']=theta
        frames.append(frame)
    return pd.concat(frames,ignore_index=True)


def stream_stochastic_to_disk(cases: list[Case], directory, *, forms=FORMS,
                     distributions=('poisson','nbinom'),replicas=1000,
                     seed=20261114,theta=10.,price_rounding='full',
                     prefix='estocastico',progress=None) -> dict:
    """Bounded-memory case-by-case Monte Carlo for large factorial designs.

    Writes per-replica CSV incrementally, with per-case summary/paired/winning
    files. Optional Parquet uses a streaming writer when pyarrow is available.
    Each result uses the same common-uniform index as run_stochastic(cases).
    """
    from pathlib import Path
    from .reports import save_frame
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    names={'evaluations':f'{prefix}_evaluaciones.csv',
           'summary':f'{prefix}_resumen.csv',
           'paired':f'{prefix}_comparaciones_pareadas.csv',
           'winning':f'{prefix}_politica_ganadora.csv',
           'convergence':f'{prefix}_convergencia_por_caso.csv'}
    targets={name:directory/path for name,path in names.items()}
    for target in targets.values():
        target.unlink(missing_ok=True)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
        have_parquet=True
    except ImportError:
        have_parquet=False
    parquet_writer=None
    total_rows=0
    try:
        for i,case in enumerate(cases):
            frame=run_stochastic([case],forms=forms,distributions=distributions,
                       replicas=replicas,seed=seed,theta=theta,price_rounding=price_rounding,
                       case_index_offset=i)
            summary=summarize_results(frame)
            pairs=paired_comparisons(frame)
            wins=winning_policy_frequency(frame)
            converged,_,_=convergence_check(frame)
            status=pd.DataFrame([{'product_id':case.product.id,'scale':case.scale,
                                 'scenario':case.scenario,'replicas':replicas,
                                 'all_ci_converged':converged,
                                 'note':'No afirmar ganancias seguras si IC incluye cero'}])
            chunks={'evaluations':frame,'summary':summary,'paired':pairs,
                    'winning':wins,'convergence':status}
            for name,data in chunks.items():
                path=targets[name]
                data.to_csv(path,mode='a',header=not path.exists(),index=False,
                            encoding='utf-8-sig' if not path.exists() else 'utf-8',
                            float_format='%.17g')
            if have_parquet:
                table=pa.Table.from_pandas(frame,preserve_index=False)
                if parquet_writer is None:
                    parquet_writer=pq.ParquetWriter(directory/f'{prefix}_evaluaciones.parquet',table.schema)
                parquet_writer.write_table(table)
            total_rows+=len(frame)
            if progress:
                progress(i+1,len(cases))
    finally:
        if parquet_writer is not None:
            parquet_writer.close()
    return {'count':total_rows,'cases':len(cases),'paths':{k:str(v) for k,v in targets.items()},
            'parquet_written':have_parquet}
