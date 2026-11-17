"""Two demand response models, freshness and exact integer rounding."""
from __future__ import annotations
from functools import lru_cache
import math
import numpy as np
from scipy.optimize import brentq
from scipy.special import expit
from .model import Case


def half_up(x: float) -> int:
    """Round nonnegative values to the nearest integer; halves round upward."""
    if not math.isfinite(x) or x < 0:
        raise ValueError("Se requiere una demanda real finita no negativa")
    return math.floor(x + 0.5)


def freshness(life: int, age: int, beta: float) -> float:
    if life <= 0 or age < 0 or age >= life or beta <= 0:
        raise ValueError("Antiguedad o vida util incompatibles")
    return 1 - (age / life) ** beta


def freshness_ratio(case: Case, t: int) -> float:
    if not 1 <= t <= case.window:
        raise ValueError("Dia fuera de la ventana de descuento")
    p = case.product
    a0 = p.life - p.window
    return freshness(p.life, a0 + t - 1, p.beta) / freshness(p.life, a0, p.beta)


@lru_cache(maxsize=512)
def alpha_to_b(alpha: float, p0: float) -> float:
    """Solve z*sigmoid(z)=alpha with z=b*p0, z>0."""
    if alpha <= 0 or p0 <= 0:
        raise ValueError("Elasticidad y precio positivos requeridos")
    upper = max(10., 2. * alpha + 10.)
    z = brentq(lambda z: z * expit(z) - alpha, 0., upper, xtol=1e-13)
    return z / p0


def mean_demand(case: Case, t: int, price: float, form: str) -> float:
    p = case.product
    if not (0 < price <= p.p0):
        raise ValueError("Precio fuera del rango admisible (0,p0]")
    h = freshness_ratio(case, t)
    baseline = case.lam * case.k * h
    if form == "B":
        factor = (price / p.p0) ** (-p.alpha)
    elif form == "C":
        b = alpha_to_b(p.alpha, p.p0)
        # Equivalent to (1+exp(bp0))/(1+exp(bp)) but numerically stable.
        log_ratio = float(np.logaddexp(0, b * p.p0) - np.logaddexp(0, b * price))
        factor = math.exp(log_ratio)
    else:
        raise ValueError("Modelo de demanda debe ser B o C")
    ans = baseline * factor
    if not math.isfinite(ans) or ans < 0:
        raise ValueError("Media invalida")
    return ans


def base_demand_sum(lam: float, product) -> float:
    """Reference demand BEFORE rotation k; includes freshness over all days."""
    a0 = product.life - product.window
    first = freshness(product.life, a0, product.beta)
    return lam * sum(freshness(product.life, a0 + t - 1, product.beta) / first
                     for t in range(1, product.window + 1))
