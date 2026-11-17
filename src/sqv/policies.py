"""Fixed policies and receding-horizon exact enumeration for policy P3."""
from __future__ import annotations
from itertools import product as cartesian
from functools import lru_cache
from .model import Case, DISCOUNTS, POLICIES

EPS = 1e-9


def fixed_discount(case: Case, policy: str, block: int) -> float:
    if policy == 'P0': return 0.
    if policy == 'P1': return .20
    if policy == 'P2':
        return (.10,.30)[block] if case.nblocks == 2 else (.10,.20,.30)[block]
    raise ValueError('Descuento fijo solo para P0, P1 y P2')


def choose_p3(case: Case, block: int, stock: int, form: str,
              *, demand_table: dict | None = None, memo: dict | None = None,
              eps: float = EPS) -> float:
    """Exhaustive enumeration on remaining blocks; apply only first action.

    Forecasts are deterministic even when realized future sales are stochastic.
    Decisions are memoized by case/form/block/observed integer stock/table mode.
    """
    if not 0 <= block < case.nblocks or not isinstance(stock, int) or stock < 0:
        raise ValueError('Bloque o inventario invalido')
    if demand_table is None:
        from .engine import demand_table as build_demand_table
        demand_table = build_demand_table(case, form)
    key = (case, form, block, stock, id(demand_table))
    if memo is not None and key in memo:
        return memo[key]
    best_revenue = -float('inf')
    best_seq = None
    for seq in cartesian(DISCOUNTS, repeat=case.nblocks-block):
        units, revenue = stock, 0.0
        for j, disc in enumerate(seq, start=block):
            for t in case.days_of_block(j):
                price, _mu, expected = demand_table[(t,disc)]
                sold = min(units, expected)
                units -= sold
                revenue += price * sold
                if units == 0:
                    break
            if units == 0:
                break
        # Cartesian order is ascending and lexicographic. Strict > retains
        # lowest first discount / lexicographically smallest sequence on ties.
        if revenue > best_revenue + eps:
            best_revenue, best_seq = revenue, seq
    answer = float(best_seq[0])
    if memo is not None:
        memo[key] = answer
    return answer
