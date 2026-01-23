from __future__ import annotations
from typing import Dict, List
from .base import CoherenceRule

_REGISTRY: Dict[str, CoherenceRule] = {}


def register(rule_cls):
    rule = rule_cls()
    if not getattr(rule, "name", None):
        raise ValueError("Rule must have non-empty .name")
    if rule.name in _REGISTRY:
        raise ValueError(f"Duplicate rule name: {rule.name}")
    _REGISTRY[rule.name] = rule
    return rule_cls


def get_rules(selected: List[str] | None = None) -> List[CoherenceRule]:
    if selected:
        missing = [n for n in selected if n not in _REGISTRY]
        if missing:
            raise ValueError(f"Unknown rules {missing}. Available: {sorted(_REGISTRY.keys())}")
        return [_REGISTRY[n] for n in selected]
    return [_REGISTRY[k] for k in sorted(_REGISTRY.keys())]


def available_rule_names() -> List[str]:
    return sorted(_REGISTRY.keys())
