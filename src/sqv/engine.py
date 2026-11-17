"""Daily inventory simulator: sales and monetary accounting."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from typing import Sequence
import math
from .model import Case, SimulationResult, DayRecord, DISCOUNTS, POLICIES
from .demand import mean_demand, half_up
from .policies import fixed_discount, choose_p3
from .stochastic import inverse_count


def price_at_discount(price0: float, discount: float, rounding: str = 'full') -> float:
    raw = price0 * (1-discount)
    if rounding == 'full': return raw
    if rounding == 'cents':
        return float(Decimal(str(raw)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
    raise ValueError("price_rounding debe ser 'full' o 'cents'")


@lru_cache(maxsize=1000)
def demand_table(case: Case, form: str, rounding: str='full') -> dict:
    """Daily (price, mean demand, integer forecast) for the 7 policy prices."""
    table = {}
    for t in range(1, case.window + 1):
        for d in DISCOUNTS:
            price = price_at_discount(case.p0, d, rounding)
            mu = mean_demand(case, t, price, form)
            table[(t,d)] = (price, mu, half_up(mu))
    return table


def simulate(case: Case, policy: str, form: str,
             shocks: Sequence[float] | None = None,
             *, distribution: str = 'deterministic', theta: float=10.,
             memo: dict | None = None, price_rounding: str='full',
             seed: int | None = None, replication: int | None = None,
             decision_form: str | None = None) -> SimulationResult:
    """One product-lot trajectory. `shocks` are common uniforms, NOT demands."""
    if policy not in POLICIES:
        raise ValueError('Politica invalida')
    if form not in ('B','C'):
        raise ValueError('Modelo invalido')
    if distribution != 'deterministic' and (shocks is None or len(shocks)!=case.window):
        raise ValueError('Simulation stochastic requires one uniform per day')
    table = demand_table(case,form,price_rounding)
    decision_form = decision_form or form
    if decision_form not in ('B','C'):
        raise ValueError('Modelo de decision invalido')
    forecast_table = demand_table(case,decision_form,price_rounding)
    stock, revenue, records = case.stock0, 0., []
    for j in range(case.nblocks):
        discount = choose_p3(case,j,stock,decision_form,demand_table=forecast_table,memo=memo) if policy=='P3' else fixed_discount(case,policy,j)
        for t in case.days_of_block(j):
            price, mu, expected = table[(t,discount)]
            demand = expected if distribution == 'deterministic' else inverse_count(float(shocks[t-1]),mu,distribution,theta)
            qty = min(stock,demand)
            next_stock = stock-qty
            income = price*qty
            records.append(DayRecord(t=t,block=j,stock_before=stock,
                                     discount=discount,price=price,mean_demand=mu,
                                     demand=demand,sold=qty,stock_after=next_stock,
                                     revenue=income))
            stock=next_stock
            revenue+=income
    reference = case.stock0 * case.p0
    loss = reference-revenue
    if loss < -1e-7:
        raise ArithmeticError('Revenue exceeded maximum regular-price inventory value')
    loss=max(0.,loss)
    return SimulationResult(case=case,form=form,policy=policy,distribution=distribution,
                            seed=seed,replication=replication,trajectory=tuple(records),
                            revenue=revenue,loss_soles=loss,
                            loss_relative=(loss/reference if reference>0 else 0.),
                            sold=case.stock0-stock,remaining=stock,rounding=price_rounding,
                            decision_form=decision_form,
                            theta=theta if distribution in ('nbinom','negative_binomial') else None)


def trace_records(result: SimulationResult) -> list[dict]:
    meta = result.summary()
    return [{**meta, 'day':r.t, 'block':r.block+1, 'stock_before':r.stock_before,
             'discount':r.discount, 'price_soles':r.price, 'mean_demand':r.mean_demand,
             'integer_demand':r.demand, 'sold_day':r.sold,'stock_after':r.stock_after,
             'revenue_day_soles':r.revenue} for r in result.trajectory]
