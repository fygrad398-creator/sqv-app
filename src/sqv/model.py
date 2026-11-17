"""Validated, immutable parameters for the simulation engine."""
from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Literal
import math

SCENARIO_K = (0.70, 1.0, 1.30)
SCENARIO_S = (0.75, 1.0, 1.50)
SCALE_LAMBDA = {"pequena": 5.0, "mediana": 15.0, "grande": 30.0}
ALPHA_BY_CATEGORY = {"Panaderia": 0.81, "Embutidos": 0.73, "Lacteos": 1.02}
WINDOW_BLOCKS = {2: (1, 1), 3: (1, 1, 1), 10: (4, 3, 3), 15: (6, 5, 4)}
DISCOUNTS = (0., .05, .10, .15, .20, .25, .30)
FORMS = ("B", "C")
POLICIES = ("P0", "P1", "P2", "P3")

@dataclass(frozen=True, slots=True)
class Product:
    id: str
    name: str
    category: str
    p0: float
    life: int
    window: int
    blocks: tuple[int, ...]
    alpha: float
    beta: float = 2.0
    weight: float = 1.0
    source: str = "synthetic"
    sensitivity_flag: bool = False

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("Producto sin ID/nombre")
        if self.category not in ALPHA_BY_CATEGORY:
            raise ValueError(f"Categoria invalida: {self.category}")
        if any(not math.isfinite(float(v)) for v in (self.p0, self.alpha, self.beta, self.weight)):
            raise ValueError("Parametro de producto no finito")
        if self.p0 <= 0 or self.alpha <= 0 or self.beta <= 0 or self.weight <= 0:
            raise ValueError(f"Precio/elasticidad/beta/peso deben ser positivos: {self.id}")
        if self.window not in WINDOW_BLOCKS or self.blocks != WINDOW_BLOCKS[self.window]:
            raise ValueError(f"Ventana y bloques incompatibles en {self.id}; esperado {WINDOW_BLOCKS.get(self.window)}")
        if self.life < self.window:
            raise ValueError(f"Vida util < ventana en {self.id}")
        if self.source not in ("synthetic", "observed", "reference"):
            raise ValueError("source debe ser synthetic, observed o reference")

@dataclass(frozen=True, slots=True)
class Case:
    product: Product
    scale: str
    scenario: str
    k: float
    s: float
    lam: float
    base_demand: float
    stock0: int
    r_target: float
    r_effective: float

    @property
    def id(self) -> str:
        return f"{self.product.id}|{self.scale}|{self.scenario}|{self.product.beta:g}|{self.product.alpha:g}|{self.lam:g}|{self.stock0}"
    @property
    def p0(self) -> float:
        return self.product.p0
    @property
    def window(self) -> int:
        return self.product.window
    @property
    def blocks(self) -> tuple[int, ...]:
        return self.product.blocks
    @property
    def nblocks(self) -> int:
        return len(self.blocks)
    def days_of_block(self, block: int) -> range:
        if not 0 <= block < self.nblocks:
            raise IndexError("Subventana fuera de rango")
        start = sum(self.blocks[:block]) + 1
        return range(start, start + self.blocks[block])

@dataclass(frozen=True, slots=True)
class DayRecord:
    t: int
    block: int
    stock_before: int
    discount: float
    price: float
    mean_demand: float
    demand: int
    sold: int
    stock_after: int
    revenue: float

@dataclass(frozen=True, slots=True)
class SimulationResult:
    case: Case
    form: str
    policy: str
    distribution: str
    seed: int | None
    replication: int | None
    trajectory: tuple[DayRecord, ...]
    revenue: float
    loss_soles: float
    loss_relative: float
    sold: int
    remaining: int
    rounding: str
    decision_form: str | None = None
    theta: float | None = None

    def summary(self) -> dict:
        c = self.case
        return {
            "product_id": c.product.id, "product_name": c.product.name,
            "category": c.product.category, "source": c.product.source,
            "validation_status": {
                "synthetic": "DEMO_SYNTHETIC",
                "reference": "REFERENCE_INPUTS_UNVERIFIED",
                "observed": "OBSERVED_INPUTS_MODELLED_DEMAND",
            }[c.product.source],
            "scenario": c.scenario, "scale": c.scale, "model": self.form,
            "policy": self.policy, "distribution": self.distribution,
            "decision_model": self.decision_form or self.form,
            "alpha": c.product.alpha, "beta": c.product.beta,
            "weight": c.product.weight, "lambda": c.lam,
            "theta": self.theta, "price_regular_soles": c.p0,
            "life_days": c.product.life, "window_days": c.window,
            "blocks": "/".join(map(str, c.blocks)),
            "sensitivity_flag": c.product.sensitivity_flag,
            "base_demand": c.base_demand,
            "stock_factor": c.s, "rotation_factor": c.k,
            "r_target": c.r_target, "r_effective": c.r_effective,
            "stock_initial": c.stock0, "sold": self.sold,
            "remaining": self.remaining, "revenue_soles": self.revenue,
            "loss_soles": self.loss_soles, "loss_relative": self.loss_relative,
            "discount_trajectory": "-".join(f"{100*x.discount:.0f}" for x in self.trajectory),
            "seed": self.seed, "replication": self.replication,
            "price_rounding": self.rounding,
        }
