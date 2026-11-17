"""Normalized 3-by-3 stock/rotation experimental scenarios."""
from __future__ import annotations
from dataclasses import replace
import math
from .model import Case, Product, SCENARIO_K, SCENARIO_S, SCALE_LAMBDA
from .demand import half_up, base_demand_sum


def build_cases(products: list[Product],
                scales: dict[str,float] | None = None,
                k_values: tuple[float,...] = SCENARIO_K,
                s_values: tuple[float,...] = SCENARIO_S,
                *, normalize_weights: bool = False) -> list[Case]:
    """Generate product x scale x E1..E9, with scenario indices in the guide."""
    if not products:
        raise ValueError("Lista vacia")
    scales = scales or SCALE_LAMBDA
    if len(k_values) != 3 or len(s_values) != 3 or any(x <= 0 for x in (*k_values,*s_values)):
        raise ValueError("Se requieren 3 factores k y 3 factores s positivos")
    wmean = sum(p.weight for p in products) / len(products)
    if abs(wmean - 1.0) > 1e-8:
        if not normalize_weights:
            raise ValueError("La media de los pesos wi debe ser 1; habilite normalize_weights")
        products = [replace(p, weight=p.weight/wmean) for p in products]
    cases = []
    for product in products:
        for scale, reference in scales.items():
            if not math.isfinite(reference) or reference <= 0:
                raise ValueError("Escala lambda invalida")
            lam = reference * product.weight
            b = base_demand_sum(lam, product)
            for i, k in enumerate(k_values):
                for j, s in enumerate(s_values):
                    scenario = f"E{1+3*i+j}"
                    stock = max(1, half_up(s * b)) if b > 0 else 0
                    cases.append(Case(product=product,scale=scale,scenario=scenario,
                                      k=k,s=s,lam=lam,base_demand=b,stock0=stock,
                                      r_target=s/k,r_effective=stock/(k*b) if b*k else float('nan')))
    return cases
