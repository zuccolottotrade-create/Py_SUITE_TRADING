from __future__ import annotations
import importlib

_RULE_MODULES = [
    "r_ohlc_basic",
    "r_price_sanity",
    "r_volume_sanity",
    "volume_zero",
    "r_ohlc_all_equal",
    "r_ohlc_out_of_range",
    "r_duplicate_timestamp",

]

_LOADED = False


def ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    for m in _RULE_MODULES:
        importlib.import_module(f"{__name__}.{m}")
    _LOADED = True
