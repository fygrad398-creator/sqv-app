"""Academic Streamlit dashboard for the SQV simulation engine (8 views)."""
from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
from html import escape
import zipfile
import altair as alt
from io import BytesIO
import json
from pathlib import Path
import sys
import pandas as pd
import streamlit as st

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from sqv.load import load_products
from sqv.scenarios import build_cases
from sqv.model import POLICIES,FORMS,SCENARIO_K,SCENARIO_S
from sqv.engine import simulate,trace_records
from sqv.experiments import (run_deterministic,run_stochastic,summarize_results,
                             paired_comparisons,winning_policy_frequency,
                             convergence_check, run_adaptive, run_cross_calibration)


st.set_page_config(page_title='SQV | Laboratorio de simulacion',page_icon='📉',layout='wide',initial_sidebar_state='expanded')
st.markdown('<style>'+ (ROOT/'assets/dashboard.css').read_text()+'</style>',unsafe_allow_html=True)
st.markdown('<div class="sqv-topline"><span>SQV / Laboratorio de investigación</span><span class="sqv-status">Experimento reproducible · v1.2</span></div>',unsafe_allow_html=True)
st.markdown('<div class="sqv-hero"><div><div class="sqv-eyebrow">Decisiones de precio, con evidencia</div><h1>Menos vencimiento.<br><em>Mejores decisiones.</em></h1><p>Explora cómo el inventario, la frescura y el precio cambian el resultado de cuatro estrategias de descuento para productos perecederos.</p></div><div class="sqv-art" aria-hidden="true"><i></i><i></i><i></i><i></i></div></div>',unsafe_allow_html=True)

PALETTE=['#b5afc4','#b8ce75','#9d8ee1','#6852e8']
def policy_chart(frame, value, title):
    return alt.Chart(frame).mark_bar(cornerRadiusEnd=6, size=28).encode(
        x=alt.X(value+':Q', title=title), y=alt.Y('policy:N', title=None, sort=list(POLICIES)),
        color=alt.Color('policy:N', scale=alt.Scale(domain=list(POLICIES),range=PALETTE), legend=None),
        tooltip=[alt.Tooltip('policy:N',title='Política'),alt.Tooltip(value+':Q',title=title,format='.2f')]
    ).properties(height=240).configure_view(strokeWidth=0).configure_axis(gridColor='#eeecf3',labelColor='#777583',titleColor='#777583')

def request_monte_carlo():
    st.session_state.result_mode='Monte Carlo'
    st.session_state.mc_requested=True


with st.sidebar:
    st.markdown('<div class="sqv-brand"><span>↗</span> SQV studio</div><div class="sqv-brand-sub">Simulación de perecederos</div>',unsafe_allow_html=True)
    st.header('01 · Matriz de los 15 productos')
    source_path=ROOT/'Matriz_15_productos_actualizada (1) (1).xlsx'
    source_fingerprint=hashlib.sha256(source_path.read_bytes()).hexdigest()
    products=load_products(source_path,source='reference')
    source_label=source_path.name
    st.caption('Fuente única: hoja Matriz_15 del Excel proporcionado.')
    st.caption(source_label)
    st.divider()
    st.header('02 · Caso experimental')
    pid=st.selectbox('Producto',options=[p.id for p in products],
        format_func=lambda x:next(f'{p.id} · {p.name}' for p in products if p.id==x),key='product')
    scale=st.selectbox('Escala comercial experimental',options=['pequena','mediana','grande'],index=1,
        help='Demanda diaria de referencia de 5, 15 y 30 unidades; NO es venta real medida.',key='scale')
    scenario=st.selectbox('Escenario E1-E9',options=[f'E{i}' for i in range(1,10)],index=4,key='scenario')
    form=st.radio('Modelo de demanda',('B','C'),
        format_func=lambda x:'B · isoelástico' if x=='B' else 'C · logit',horizontal=True,key='model')
    rounding=st.radio('Redondeo de precio',('full','cents'),
        format_func=lambda x:'Precisión completa' if x=='full' else 'Céntimos',key='rounding')
    st.divider()
    result_mode=st.radio('Resultados que deseas ver', ['Determinista','Monte Carlo'],key='result_mode')
    st.caption('Determinista: se actualiza al cambiar el caso. Monte Carlo: aplica los cambios con el botón inferior.')
    st.header('03 · Monte Carlo')
    distribution=st.selectbox('Distribucion',('poisson','nbinom'),
        format_func=lambda x:'Poisson' if x=='poisson' else 'Binomial negativa',key='distribution')
    theta=st.number_input('Dispersion θ (experimental)',min_value=.1,max_value=1000.,
                          value=10.,step=1.,disabled=distribution=='poisson',key='theta')
    mc_mode=st.radio('Método de ejecución', ['Réplicas fijas','Parada adaptativa'],key='mc_mode')
    replicas=st.select_slider('Réplicas / límite adaptativo',options=[1000,5000,10000,50000,100000],value=1000,key='replicas')
    st.caption('IC95: semiamplitud ≤ 2 %; diferencias cercanas a cero: S/ 0,05.')
    seed=st.number_input('Semilla',min_value=1,max_value=2147483647,value=20261114,key='seed')
    st.button('Aplicar cambios y ejecutar Monte Carlo',key='run_mc_sidebar',
              on_click=request_monte_carlo,type='primary',use_container_width=True)
    parameter_key=hashlib.sha256(json.dumps([asdict(p) for p in products],sort_keys=True).encode()).hexdigest()
    experiment_key=(source_fingerprint,parameter_key,rounding)

st.markdown('<div class="sqv-warning">FUENTE ÚNICA · Los 15 productos, precios, vidas útiles, ventanas y bloques se leen del Excel proporcionado. Demanda e inventario se generan con los escenarios de la guía.</div>',unsafe_allow_html=True)

cases=build_cases(products)
case=next(c for c in cases if c.product.id==pid and c.scale==scale and c.scenario==scenario)
selection_key=(source_fingerprint,parameter_key,pid,scale,scenario,form,rounding)
mc_key=(selection_key,distribution,theta if distribution=='nbinom' else None,replicas,seed,mc_mode)
if st.session_state.pop('mc_requested',False):
    with st.spinner(f'Ejecutando Monte Carlo: hasta {replicas:,} réplicas del caso {pid} / {scenario} / {scale}...'):
        if mc_mode=='Parada adaptativa':
            mc,logs=run_adaptive([case],forms=(form,),distribution=distribution,
                stages=tuple(n for n in (1000,5000,10000,50000,100000) if n<=replicas),
                seed=int(seed),theta=float(theta),price_rounding=rounding)
        else:
            mc=run_stochastic([case],forms=(form,),distributions=(distribution,),replicas=replicas,
                seed=int(seed),theta=float(theta),price_rounding=rounding)
            logs=pd.DataFrame()
        ok,agg,pairs=convergence_check(mc)
        st.session_state.update(mc_data=mc,mc_key=mc_key,mc_logs=logs,mc_summary=agg,
                                mc_pairs=pairs,mc_converged=ok,mc_wins=winning_policy_frequency(mc))
mc_ready=st.session_state.get('mc_key')==mc_key
mc_pending=result_mode=='Monte Carlo' and not mc_ready
simulations={p:simulate(case,p,form,price_rounding=rounding) for p in POLICIES}
single=pd.DataFrame([x.summary() for x in simulations.values()])
st.markdown(f'<div class="sqv-selection"><b>{escape(case.product.name)}</b> &nbsp; / &nbsp; {escape(scale)} &nbsp; / &nbsp; {scenario} &nbsp; / &nbsp; Modelo {form}</div>',unsafe_allow_html=True)
cols=st.columns(4)
for col,(label,value) in zip(cols,[('Inventario inicial simulado',f'{case.stock0} und'),
                                   ('R efectivo',f'{case.r_effective:.2f}'),
                                   ('Precio regular',f'S/ {case.p0:.2f}'),
                                   ('Ventana',f'{case.window} días')]):
    col.metric(label,value)

st.subheader('Resultado actual · '+result_mode)
if result_mode=='Monte Carlo':
    if mc_ready:
        result_frame=st.session_state.mc_summary
        comparison_export=result_frame
        loss_column='mean'
        n=int(result_frame.n.iloc[0])
        st.success(f'Monte Carlo actualizado · {pid} · {scenario} · {scale} · {form} · {distribution} · {n:,} réplicas por política · semilla {int(seed)}')
    else:
        result_frame=None
        comparison_export=pd.DataFrame()
        st.warning('Monte Carlo pendiente de actualizar. Pulsa «Aplicar cambios y ejecutar Monte Carlo» en la barra lateral.')
else:
    result_frame=single
    comparison_export=single
    loss_column='loss_soles'
    st.caption('Cálculo determinista actualizado para el caso seleccionado. Los controles de Monte Carlo afectan la vista Monte Carlo después de ejecutar.')
if result_frame is not None:
    for col,pol in zip(st.columns(4),POLICIES):
        loss=float(result_frame.loc[result_frame.policy==pol,loss_column].iloc[0])
        col.metric(f'{pol} · pérdida '+('media' if result_mode=='Monte Carlo' else 'determinista'),f'S/ {loss:.2f}')
    st.caption('Precio y vida útil permanecen como figuran en el Excel. B y C pueden dar el mismo resultado al redondear la demanda a unidades enteras.')

(t1,t2,t3,t4,t5,t6,t7,t8)=st.tabs([
    '01 Configuración','02 Simulación','03 Inventario','04 Optimización P3',
    '05 Resultados','06 Estadística','07 Sensibilidad','08 Exportación'])

with t1:
    st.subheader('Tu experimento, de un vistazo')
    policy_cols=st.columns(4)
    for col, name, desc in zip(policy_cols,POLICIES,['Sin descuento · referencia','20 % durante toda la ventana','10 / 20 / 30 % por bloque','0–30 % · reoptimiza por bloque']):
        col.markdown(f'<div class="sqv-policy"><small>ESTRATEGIA DE PRECIO</small><strong>{name}</strong><p>{desc}</p></div>',unsafe_allow_html=True)
    st.caption('P2 usa 10 / 30 % cuando la ventana tiene dos bloques.')
    data=pd.DataFrame([{'Producto':case.product.name,'Categoría':case.product.category,
                        'Precio S/':case.p0,'Vida útil (días)':case.product.life,
                        'Ventana (días)':case.window,'Subventanas':str(case.blocks),
                        'Elasticidad |α|':case.product.alpha,'Frescura β':case.product.beta,
                        'Rotación k':case.k,'Inventario s':case.s,'λ (und/dia)':case.lam,
                        'B referencia':case.base_demand,'Stock inicial':case.stock0,
                        'R objetivo':case.r_target,'R efectivo':case.r_effective}])
    st.dataframe(data,hide_index=True,use_container_width=True)
    st.markdown('**Catalogo de los 15 productos de la matriz en uso**')
    catalogo=pd.DataFrame([{'ID':p.id,'Categoría original':p.category,
        'Producto / presentacion':p.name,'Precio (S/)':p.p0,'Vida útil en matriz (días)':p.life,
        'Ventana W (días)':p.window,'Subventanas': ' / '.join(map(str,p.blocks)),
        'Elasticidad ancla |α|':p.alpha,
        'Revisar clasificacion': 'SI' if p.sensitivity_flag else ''} for p in products])
    st.dataframe(catalogo,hide_index=True,use_container_width=True)
    st.markdown('**Cuadricula experimental E1-E9 (R teorica = s/k)**')
    matrix=pd.DataFrame([
        {**{'Rotación / stock': f'k={k:.2f}'},
         **{f's={ss:.2f}': f'E{1+i*3+j} · {ss/k:.2f}' for j,ss in enumerate(SCENARIO_S)}}
        for i,k in enumerate(SCENARIO_K)])
    st.dataframe(matrix,hide_index=True,use_container_width=True)
    if case.product.sensitivity_flag:
        st.warning('Este keke se encuentra bajo Lacteos en el Excel. Se ha conservado esa categoria y su alfa, que requiere revision.')
    st.caption('Supuestos del PDF: sin reposicion ni donaciones, retiro S/ 0, compra excluida. '
               'Los stocks de capturas en Presentacion son puntuales y NO se extrapolan a ventas mensuales.')
    st.caption('Los datos de vida util incorporados en Matriz_15 son provisionales: Presentacion solicita verificarlos contra etiquetas/fichas del fabricante.')

with t2:
    st.subheader('Ejecución científica')
    st.write('El caso seleccionado se calcula con los cuatro tratamientos P0-P3. La corrida factorial completa contiene 3.240 evaluaciones de politica.')
    c1,c2=st.columns(2)
    with c1:
        if st.button('Ejecutar matriz factorial determinista (3.240 evaluaciones)',key='run_factorial',use_container_width=True,type='primary'):
            bar=st.progress(0,text='Ejecutando matriz factorial')
            def progress(i,total):bar.progress(i/total,text=f'Caso {i}/{total}')
            with st.spinner('Calculando...'):
                full=run_deterministic(cases,progress=progress,price_rounding=rounding)
            st.session_state.factorial=full
            st.session_state.factorial_source_key=experiment_key
            st.success(f'{len(full)} evaluaciones terminadas sobre los 15 productos del Excel.')
    with c2:
        st.button('Aplicar cambios y ejecutar Monte Carlo',key='run_mc_tab',on_click=request_monte_carlo,use_container_width=True)
        st.caption('Este botón ejecuta el caso elegido en la barra lateral. El resultado aparece arriba, en «05 Resultados» y en «06 Estadística».')
    if 'factorial' in st.session_state and st.session_state.get('factorial_source_key')==experiment_key:
        full=st.session_state.factorial
        filtered=full[(full.product_id==pid)&(full.scale==scale)&(full.scenario==scenario)&(full.model==form)]
        st.markdown(f'**Factorial filtrado al caso actual: {pid} / {scenario} / {scale} / {form}**')
        st.dataframe(filtered,hide_index=True,use_container_width=True)
    st.caption('Monte Carlo con replicas y precisión cientifica completas puede tener un costo computacional considerable.')

with t3:
    st.subheader('Trazabilidad diaria · cálculo determinista')
    st.caption('Esta trayectoria usa demanda determinista. Las pérdidas medias y los intervalos de Monte Carlo están en «05 Resultados» y «06 Estadística».')
    view=[]
    for policy,result in simulations.items():
        for r in result.trajectory:
            view.append({'Día':r.t,'Política':policy,'Inventario inicial día':r.stock_before,
                         'Demanda esperada':r.mean_demand,'Demanda entera':r.demand,
                         'Ventas':r.sold,'Remanente':r.stock_after,'Precio S/':r.price,
                         'Descuento %':100*r.discount,'Ingresos S/':r.revenue})
    traces=pd.DataFrame(view)
    st.line_chart(traces.pivot(index='Día',columns='Política',values='Remanente'),y_label='Stock remanente (und)')
    st.dataframe(traces,hide_index=True,use_container_width=True)

with t4:
    st.subheader('P3 · trayectoria determinista del caso')
    st.caption('Las decisiones mostradas corresponden al cálculo determinista; Monte Carlo reoptimiza ante el inventario aleatorio de cada réplica.')
    p3=simulations['P3']
    decisions=[]
    for j in range(case.nblocks):
        entries=[r for r in p3.trajectory if r.block==j]
        decisions.append({'Subventana':j+1,'Días':f'{entries[0].t}-{entries[-1].t}',
                          'Stock observado':entries[0].stock_before,
                          'Descuento elegido (%)':100*entries[0].discount,
                          'Ventas realizadas':sum(r.sold for r in entries),
                          'Ingreso (S/)':sum(r.revenue for r in entries)})
    st.dataframe(pd.DataFrame(decisions),hide_index=True,use_container_width=True)
    st.bar_chart(pd.DataFrame({'P3 descuento (%)':[100*r.discount for r in p3.trajectory]},
                              index=[f'Dia {r.t}' for r in p3.trajectory]),y_label='Descuento (%)')
    st.caption('P3 evalua hasta 7^3=343 secuencias, aplica el descuento del bloque actual y reoptimiza al iniciar el siguiente. Puede subir, bajar o mantener el descuento.')

with t5:
    st.subheader('Comparación de políticas · '+result_mode)
    if result_frame is None:
        st.info('Aplica los cambios con el botón Monte Carlo de la barra lateral para ver la nueva comparación.')
    elif result_mode=='Monte Carlo':
        st.dataframe(result_frame[['policy','n','mean','ci_low','ci_high','mean_revenue_soles','mean_loss_relative','mean_remaining']],hide_index=True,use_container_width=True)
        st.altair_chart(policy_chart(result_frame,'mean','Pérdida potencial media (S/)'),use_container_width=True)
        baseline=float(result_frame.loc[result_frame.policy=='P0','mean'].iloc[0])
        opt=float(result_frame.loc[result_frame.policy=='P3','mean'].iloc[0])
        st.metric('Diferencia media P3 − P0',f'S/ {opt-baseline:.2f}')
    else:
        comparison=single[['policy','revenue_soles','loss_soles','loss_relative','remaining','sold','discount_trajectory']].copy()
        comparison.columns=['Política','Ingresos S/','Pérdida potencial S/','Pérdida relativa','Remanente','Vendidas','Descuentos diarios %']
        st.dataframe(comparison,hide_index=True,use_container_width=True,
                     column_config={'Pérdida relativa':st.column_config.NumberColumn(format='%.2f')})
        st.altair_chart(policy_chart(single,'loss_soles','Pérdida potencial (S/)'),use_container_width=True)
        baseline=float(single.loc[single.policy=='P0','loss_soles'].iloc[0])
        st.metric('Diferencia P3 − P0 determinista',f'S/ {p3.loss_soles-baseline:.2f}')

with t6:
    st.subheader('Incertidumbre y diferencias pareadas')
    if 'mc_data' in st.session_state and st.session_state.get('mc_key')==mc_key:
        mc=st.session_state.mc_data
        agg=st.session_state.mc_summary
        pairs=st.session_state.mc_pairs
        ok=st.session_state.mc_converged
        st.caption(f'Estado del criterio de parada para este caso: {"CONVERGE" if ok else "NO CONVERGE AUN"}. El IC que incluye 0 no acredita ganancia segura.')
        st.dataframe(agg[['policy','n','mean','sd','ci_low','ci_high','halfwidth','mean_revenue_soles']],
                     hide_index=True,use_container_width=True)
        st.markdown('**Contrastes pareados: diferencias P3 - politica base en S/**')
        st.dataframe(pairs[['comparison','n','mean','ci_low','ci_high','ci_includes_zero']],
                     hide_index=True,use_container_width=True)
        chart=alt.Chart(agg).encode(y=alt.Y('policy:N',title=None),x=alt.X('mean:Q',title='Pérdida media e IC95 (S/)'))
        points=chart.mark_point(filled=True,size=90,color='#6852e8')
        intervals=chart.mark_rule(color='#9d8ee1',strokeWidth=3).encode(x='ci_low:Q',x2='ci_high:Q')
        st.altair_chart((intervals+points).properties(height=230),use_container_width=True)
        st.markdown('**Frecuencia de política ganadora**')
        st.dataframe(st.session_state.mc_wins,hide_index=True,use_container_width=True)
        if not st.session_state.mc_logs.empty:
            st.markdown('**Convergencia por etapa**')
            st.dataframe(st.session_state.mc_logs,hide_index=True,use_container_width=True)
        if not ok:
            st.warning('Precisión pendiente: amplíe el límite de réplicas. Alcanzar el límite no implica convergencia.')
    else:
        st.info('Pulsa «Aplicar cambios y ejecutar Monte Carlo» en la barra lateral. Al cambiar el caso o los parámetros debes ejecutar de nuevo.')

with t7:
    st.subheader('Análisis local de sensibilidad')
    st.write('Un factor a la vez: frescura β, elasticidad α y especificacion de demanda B/C. Este panel no sustituye el barrido completo.')
    if st.button('Calcular sensibilidad del caso',key='run_sensitivity',use_container_width=True):
        tests=[]
        from sqv.demand import base_demand_sum,half_up
        for label, kwargs in [('β=1',{'beta':1.}),('β=2',{'beta':2.}),('β=5',{'beta':5.}),
                              ('α×0.8',{'alpha':case.product.alpha*.8}),
                              ('α×1.2',{'alpha':case.product.alpha*1.2}),
                              ('Kekes: α panadería',{'alpha':.81 if case.product.sensitivity_flag else case.product.alpha})]:
            pp=[replace(p,**kwargs) if p.id==pid else p for p in products]
            cc=next(c for c in build_cases(pp) if c.product.id==pid and c.scale==scale and c.scenario==scenario)
            for f in ('B','C'):
                for pol in POLICIES:
                    res=simulate(cc,pol,f,price_rounding=rounding)
                    tests.append({'Variante':label,'Modelo':f,'Política':pol,
                                  'Pérdida potencial S/':res.loss_soles,
                                  'Ingresos S/':res.revenue,'R efectivo':cc.r_effective})
        st.session_state.sensitivity=pd.DataFrame(tests)
        st.session_state.sensitivity_key=selection_key
    if 'sensitivity' in st.session_state and st.session_state.get('sensitivity_key')==selection_key:
        sf=st.session_state.sensitivity
        st.dataframe(sf,hide_index=True,use_container_width=True)
        st.line_chart(sf[sf.Política=='P3'].pivot(index='Variante',columns='Modelo',values='Pérdida potencial S/'))
    else:
        st.info('Seleccione "Calcular sensibilidad del caso" para ver el efecto de los supuestos.')
    st.markdown('**Prueba cruzada B ↔ C**')
    st.caption('La demanda se genera con un modelo y P3 decide con el otro, conservando el mismo inventario.')
    cross=run_cross_calibration([case],rounding=rounding)
    st.dataframe(cross[['model','decision_model','calibration_type','loss_soles','revenue_soles','discount_trajectory']],hide_index=True,use_container_width=True)
    if st.button('Evaluar dispersión binomial negativa (θ = 5, 10, 30)',use_container_width=True):
        with st.spinner('Evaluando tres escenarios de dispersion...'):
            outputs=[]
            for th in (5.,10.,30.):
                batch=run_stochastic([case],forms=(form,),distributions=('nbinom',),
                                     replicas=max(100,int(replicas)),seed=int(seed),theta=th,
                                     price_rounding=rounding)
                batch['theta_experimental']=th
                outputs.append(batch)
            sensitivity_theta=pd.concat(outputs,ignore_index=True)
        st.session_state.theta_data=sensitivity_theta
        st.session_state.theta_key=(selection_key,replicas,seed,rounding)
    if 'theta_data' in st.session_state and st.session_state.get('theta_key')==(selection_key,replicas,seed,rounding):
        theta_summary=st.session_state.theta_data.groupby(['theta_experimental','policy']).loss_soles.mean().reset_index()
        st.markdown('**Sensibilidad a la dispersion (binomial negativa)**')
        st.dataframe(theta_summary,hide_index=True,use_container_width=True)
        st.line_chart(theta_summary.pivot(index='theta_experimental',columns='policy',values='loss_soles'))

with t8:
    st.subheader('Descarga de evidencias y configuracion')
    st.download_button('Descargar comparacion del caso (CSV)',comparison_export.to_csv(index=False).encode('utf-8-sig'),
                       file_name='sqv_caso_politicas.csv',mime='text/csv',use_container_width=True,disabled=mc_pending)
    detail=pd.DataFrame([rec for x in simulations.values() for rec in trace_records(x)])
    st.download_button('Descargar trazabilidad determinista (CSV)',detail.to_csv(index=False).encode('utf-8-sig'),
                       file_name='sqv_trazabilidad.csv',mime='text/csv',use_container_width=True)
    if mc_ready:
        if st.button('Preparar CSV de réplicas',key='prepare_mc_csv'):
            st.session_state.mc_csv=st.session_state.mc_data.to_csv(index=False,float_format='%.17g').encode('utf-8-sig')
            st.session_state.mc_csv_key=mc_key
        if st.session_state.get('mc_csv_key')==mc_key:
            st.download_button('Descargar Monte Carlo (CSV)',st.session_state.mc_csv,
                               file_name='sqv_montecarlo.csv',mime='text/csv',use_container_width=True)
    if 'factorial' in st.session_state and st.session_state.get('factorial_source_key')==experiment_key:
        st.download_button('Descargar factorial completo (CSV)',st.session_state.factorial.to_csv(index=False).encode('utf-8-sig'),
                           file_name='sqv_factorial.csv',mime='text/csv',use_container_width=True)
    parameters={'product_id':pid,'scale':scale,'scenario':scenario,'model':form,
                'distribution':distribution,'theta':theta,'replicas':replicas,'seed':int(seed),
                'source_status':'REFERENCE_UNVERIFIED',
                'source_file':source_label, 'source_sha256':source_fingerprint,
                'economic_indicator':'potencial de ingresos no realizado; NO perdida contable',
                'alpha_by_category':{key:next(p.alpha for p in products if p.category==key) for key in ('Panaderia','Embutidos','Lacteos')},
                'stock_generated_from_scenarios':True,
                'rounding':rounding,'display_mode':result_mode,'monte_carlo_matches_controls':mc_ready,
                'mc_mode':mc_mode,'relative_tolerance':.02,'absolute_tolerance_soles':.05,
                'products':[asdict(p) for p in products]}
    st.download_button('Descargar configuracion (JSON)',json.dumps(parameters,indent=2,ensure_ascii=False),
                       file_name='sqv_configuracion.json',mime='application/json',use_container_width=True)
    export_key=(result_mode,mc_key,mc_ready)
    if st.button('Preparar expediente del experimento (ZIP)',key='prepare_zip',disabled=mc_pending):
        bundle=BytesIO()
        with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('configuracion.json',json.dumps(parameters,indent=2,ensure_ascii=False))
            archive.writestr('comparacion.csv',comparison_export.to_csv(index=False,float_format='%.17g'))
            archive.writestr('trazabilidad.csv',detail.to_csv(index=False,float_format='%.17g'))
            archive.writestr('matriz_normalizada.json',json.dumps(parameters['products'],indent=2,ensure_ascii=False))
            for path in sorted((ROOT/'src/sqv').glob('*.py')):
                archive.writestr('codigo/'+path.name,path.read_bytes())
            if st.session_state.get('mc_key')==mc_key:
                mc=st.session_state.mc_data
                archive.writestr('monte_carlo.csv',mc.to_csv(index=False,float_format='%.17g'))
                archive.writestr('intervalos.csv',summarize_results(mc).to_csv(index=False))
                archive.writestr('comparaciones_pareadas.csv',paired_comparisons(mc).to_csv(index=False))
                archive.writestr('convergencia.csv',st.session_state.mc_logs.to_csv(index=False))
        st.session_state.experiment_zip=bundle.getvalue()
        st.session_state.experiment_zip_key=export_key
    if st.session_state.get('experiment_zip_key')==export_key:
        st.download_button('Descargar expediente del experimento (ZIP)',st.session_state.experiment_zip,
            file_name='SQV_experimento.zip',mime='application/zip',type='primary',use_container_width=True,disabled=mc_pending)
    st.caption('Las descargas de réplicas y del expediente se preparan al pulsar su botón. CSV conserva precisión completa.')
