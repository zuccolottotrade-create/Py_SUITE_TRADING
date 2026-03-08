"""
Applicazione mutazioni al config_strategy (DataFrame CONDITIONS), senza cambiare colonne.
"""Mutatori minimi parametri."""

Responsabilità:
- applicare params -> rhs_value (EU), enabled, shift (opz.)
- agire solo su righe del blocco regime target (o blocchi attivi)
"""
from __future__ import annotations

from typing import Dict, Mapping


def mutate_params(base: Mapping[str, float], updates: Mapping[str, float]) -> Dict[str, float]:
    out = {k: float(v) for k, v in base.items()}
    for key, value in updates.items():
        out[key] = float(value)
    return out"""
Applicazione mutazioni al config_strategy (DataFrame CONDITIONS), senza cambiare colonne.

Responsabilità:
- applicare params -> rhs_value (EU), enabled, shift (opz.)
- agire solo su righe del blocco regime target (o blocchi attivi)
"""
