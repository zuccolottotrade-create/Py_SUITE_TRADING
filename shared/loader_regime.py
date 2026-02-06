from __future__ import annotations

from importlib import util as importlib_util
from pathlib import Path
from types import ModuleType
from typing import Callable

import pandas as pd


def list_regime_modules(shared_dir: Path) -> list[str]:
    """
    Elenca i moduli selezionabili.
    Convenzione: shared/regime_*.py (es: regime_classifier_1.py)
    Ritorna lo stem del file (senza .py).
    """
    shared_dir = Path(shared_dir).resolve()

    return sorted(
        p.stem
        for p in shared_dir.glob("regime_*.py")
        if p.is_file()
        and not p.name.startswith("__")
        and p.name != "loader_regime.py"
    )


def _load_module_from_path(module_name: str, path: Path) -> ModuleType:
    spec = importlib_util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Impossibile creare spec per {module_name} da {path}")

    mod = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def load_regime_apply(shared_dir: Path, module_name: str) -> Callable[[pd.DataFrame], pd.DataFrame]:
    """
    Carica un filtro dalla cartella shared/ e ritorna la funzione callable:
    - preferisce apply_regime(df) (nuova convenzione)
    - fallback su apply(df) (retrocompatibilità)
    """

    shared_dir = Path(shared_dir).resolve()
    path = (shared_dir / f"{module_name}.py").resolve()

    if not path.exists():
        raise FileNotFoundError(f"Modulo regime non trovato: {path}")

    mod = _load_module_from_path(module_name, path)

    apply_fn = getattr(mod, "apply_regime", None) or getattr(mod, "apply", None)
    if apply_fn is None:
        raise ValueError(f"Modulo regime '{module_name}' senza apply_regime/apply")

    return apply_fn

