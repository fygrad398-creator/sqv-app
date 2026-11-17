"""Exact quantile coupling with common random numbers across pricing policies."""
from __future__ import annotations
import math
import numpy as np
from scipy.stats import poisson, nbinom


def inverse_count(u: float, mu: float, distribution: str, theta: float=10.) -> int:
    if not (0 <= u < 1) or not math.isfinite(u):
        raise ValueError('Uniforme debe pertenecer a [0,1)')
    if not math.isfinite(mu) or mu<0:
        raise ValueError('Media de demanda invalida')
    if mu == 0 or u == 0:
        return 0
    if distribution == 'poisson':
        value = poisson.ppf(u,mu)
    elif distribution in ('nbinom','negative_binomial'):
        if not math.isfinite(theta) or theta<=0:
            raise ValueError('Dispersion theta debe ser positiva')
        # nbinom with mean mu and variance mu+mu^2/theta.
        value = nbinom.ppf(u,theta,theta/(theta+mu))
    else:
        raise ValueError('Distribucion debe ser poisson o nbinom')
    if not np.isfinite(value):
        raise ArithmeticError('Cuantil de demanda no finito')
    return int(value)


def common_uniforms(seed: int, case_index: int, distribution_index: int,
                    replicas: int, window: int) -> np.ndarray:
    """Per-case, per-distribution reproducible uniform random numbers."""
    if replicas <= 0 or window <=0:
        raise ValueError('replicas/window deben ser positivos')
    rng = np.random.default_rng(np.random.SeedSequence([seed,case_index,distribution_index]))
    return rng.random((replicas,window))
